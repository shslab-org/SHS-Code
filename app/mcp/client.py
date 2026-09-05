from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from app.logger import logger
from app.schema import ToolResult
from app.tool.base import BaseTool, ToolCollection


class MCPProxyTool(BaseTool):
    """A local proxy for a remote MCP tool."""

    def __init__(self, name: str, description: str, input_schema: dict, client: "MCPClient") -> None:
        self.name = name
        self.description = description
        self.parameters = input_schema
        self._client = client

    async def execute(self, **kwargs: Any) -> ToolResult:
        return await self._client.call_tool(self.name, kwargs)


class MCPClient:
    """Connects to an MCP server via stdio or SSE and proxies its tools."""

    def __init__(self, name: str, transport: str = "stdio",
                 command: Optional[str] = None, args: Optional[list[str]] = None,
                 url: Optional[str] = None) -> None:
        self.name = name
        self.transport = transport
        self.command = command
        self.args = args or []
        self.url = url
        self._tools: ToolCollection = ToolCollection()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._connected = False
        # SHS Code FIX: serialize JSON-RPC round-trips on one client so
        # concurrent tool calls cannot interleave reads/writes.
        self._rpc_lock = asyncio.Lock()

    async def connect(self) -> ToolCollection:
        try:
            if self.transport == "stdio":
                await self._connect_stdio()
            elif self.transport == "sse":
                await self._connect_sse()
            else:
                raise ValueError(f"Unknown transport: {self.transport}")
        except BaseException:
            # v3.1 FIX (orphaned MCP server): the subprocess is spawned BEFORE
            # the handshake — a failed/timed-out/cancelled handshake used to
            # drop the client with the server process still running (one
            # orphan per agent run on a flaky server). Kill it here.
            # BaseException: asyncio.wait_for cancellation must clean up too.
            try:
                await self.disconnect()
            except Exception:
                pass
            raise
        self._connected = True
        return self._tools

    async def _connect_stdio(self) -> None:
        if not self.command:
            raise ValueError("command required for stdio transport")
        cmd = [self.command] + self.args
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # SHS Code FIX (spec §24): drain stderr continuously so chatty MCP
        # servers can never deadlock the pipe buffer.
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        # SHS Code FIX (spec §24): proper MCP initialize handshake before
        # tools/list — standard MCP servers reject requests without it.
        await self._initialize()
        tools_raw = await self._rpc("tools/list", {})
        self._register_tools(tools_raw.get("tools", []))
        logger.info(f"[MCP:{self.name}] Connected via stdio, {len(self._tools)} tools.")

    async def _drain_stderr(self) -> None:
        """Continuously consume the child's stderr; log at debug level."""
        try:
            assert self._process and self._process.stderr
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if text:
                    logger.debug(f"[MCP:{self.name}] stderr: {text}")
        except Exception:
            pass

    async def _initialize(self) -> None:
        """MCP initialize handshake (JSON-RPC). Non-fatal on homemade servers
        that don't implement it — fall back to direct tools/list."""
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "shs-code", "version": "1.0.0"},
        }
        try:
            await self._rpc("initialize", params)
            # notifications/initialized is fire-and-forget per spec
            assert self._process and self._process.stdin
            note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._process.stdin.write((note + "\n").encode())
            await self._process.stdin.drain()
        except Exception as e:
            logger.debug(f"[MCP:{self.name}] initialize handshake skipped ({e}) — "
                         f"server may be a simple JSON-RPC tool host")

    async def _connect_sse(self) -> None:
        if not self.url:
            raise ValueError("url required for SSE transport")
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/tools/list", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
            self._register_tools(data.get("tools", []))
            logger.info(f"[MCP:{self.name}] Connected via SSE, {len(self._tools)} tools.")
        except Exception as e:
            logger.error(f"[MCP:{self.name}] SSE connection failed: {e}")
            raise

    def _register_tools(self, tools_raw: list[dict]) -> None:
        for t in tools_raw:
            proxy = MCPProxyTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
                client=self,
            )
            self._tools.add(proxy)

    async def _rpc(self, method: str, params: dict) -> dict:
        # SHS Code FIX (response correlation): the loop returned the FIRST
        # line containing any "id" — concurrent tool calls swapped responses,
        # and server-initiated requests were misread as responses. The
        # response id is now matched to the REQUEST id, and a lock
        # serializes RPCs on one client.
        if not self._process:
            return {}
        request_id = str(uuid.uuid4())
        msg = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        async with self._rpc_lock:
            assert self._process.stdin
            self._process.stdin.write((msg + "\n").encode())
            await self._process.stdin.drain()
            assert self._process.stdout
            for _ in range(16):
                try:
                    line = await asyncio.wait_for(self._process.stdout.readline(), timeout=15)
                except asyncio.TimeoutError:
                    logger.warning(f"[MCP:{self.name}] RPC timeout waiting for id {request_id}")
                    return {}
                if not line:
                    return {}
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue  # non-JSON noise line
                if data.get("id") != request_id:
                    continue  # notification / someone else's response / server request
                if "error" in data:
                    raise RuntimeError(f"MCP error: {data['error']}")
                return data.get("result", {})
        return {}

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        if self.transport == "stdio":
            result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
            content = result.get("content", [{}])
            text = content[0].get("text", "") if content else ""
            return ToolResult(output=text)
        elif self.transport == "sse":
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.url}/tools/call",
                        json={"name": name, "arguments": arguments},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        # SHS Code FIX: HTTP status was never checked — a 4xx/5xx
                        # body became the tool OUTPUT, reporting failures as
                        # successful calls with garbage content.
                        if resp.status != 200:
                            body = (await resp.text())[:300]
                            return ToolResult(
                                error=f"MCP SSE call failed: HTTP {resp.status} — {body}")
                        data = await resp.json()
                if data.get("isError"):
                    content = data.get("content", [{}])
                    text = content[0].get("text", "") if content else ""
                    return ToolResult(error=f"MCP tool error: {text[:500]}")
                content = data.get("content", [{}])
                text = content[0].get("text", "") if content else ""
                return ToolResult(output=text)
            except Exception as e:
                return ToolResult(error=str(e))
        return ToolResult(error="Not connected")

    async def disconnect(self) -> None:
        # v3.1 FIX (kill escalation + transport close): terminate alone can
        # leave the server running (orphan) when it ignores SIGTERM, and the
        # pipe transports were never closed on ANY path — the source of the
        # "Event loop is closed" __del__ noise. Escalate to SIGKILL and close
        # transports deterministically.
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self._process is not None:
            try:
                if self._process.returncode is None:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5)
                    except Exception:
                        try:
                            self._process.kill()
                            await asyncio.wait_for(self._process.wait(), timeout=3)
                        except Exception:
                            pass
                # close pipe transports (all paths, incl. already-exited)
                for stream in (self._process.stdin, self._process.stdout,
                                self._process.stderr):
                    try:
                        if stream is not None:
                            stream.close()
                    except Exception:
                        pass
                try:
                    transport = getattr(self._process, "_transport", None)
                    if transport is not None:
                        transport.close()
                except Exception:
                    pass
            except Exception:
                pass
        self._connected = False
