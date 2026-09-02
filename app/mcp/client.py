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

    async def connect(self) -> ToolCollection:
        if self.transport == "stdio":
            await self._connect_stdio()
        elif self.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.transport}")
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
        if not self._process:
            return {}
        msg = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params})
        assert self._process.stdin
        self._process.stdin.write((msg + "\n").encode())
        await self._process.stdin.drain()
        assert self._process.stdout
        # SHS Code FIX: skip notification responses (no "id") that some MCP
        # servers emit between request responses.
        for _ in range(8):
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=15)
            if not line:
                return {}
            data = json.loads(line)
            if "id" in data:
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
                        data = await resp.json()
                content = data.get("content", [{}])
                text = content[0].get("text", "") if content else ""
                return ToolResult(output=text)
            except Exception as e:
                return ToolResult(error=str(e))
        return ToolResult(error="Not connected")

    async def disconnect(self) -> None:
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except Exception:
                pass
        self._connected = False
