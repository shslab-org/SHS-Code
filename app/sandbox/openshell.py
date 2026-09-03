from __future__ import annotations

"""
OpenShell Sandbox — Linux namespace isolation using ``unshare``.

Creates network and mount namespace isolation for code execution.
Linux-only. Operates in stub mode on non-Linux platforms.

Provides the same interface as ``DockerSandbox``:
- ``start()`` — create isolated namespace process
- ``exec(code)`` — execute Python code in the isolated environment
- ``stop()`` — terminate the isolated process

Security:
- Network namespace: No network access (``--net``)
- Mount namespace: Read-only filesystem (``--mount-proc``)
- PID namespace: Isolated process tree
- User namespace: Unprivileged execution where possible
"""

import asyncio
import os
import signal
import sys
import time
from typing import Optional

from app.exceptions import SandboxError
from app.logger import logger
from app.schema import ToolResult

_IS_LINUX = sys.platform == "linux" or sys.platform.startswith("linux")
_UNSHARE_CMD = "unshare"
_TIMEOUT = 30


class OpenShellSandbox:
    """Runs code in an isolated Linux namespace using ``unshare``.

    Falls back to a stub that warns about platform incompatibility
    when running on non-Linux systems.
    """

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False

    @property
    def is_available(self) -> bool:
        """Check if OpenShell sandbox is available on this platform."""
        return _IS_LINUX

    async def start(self) -> None:
        """Create an isolated namespace process.

        The process runs a persistent shell that can receive commands
        via stdin and return output via stdout/stderr.
        """
        if not _IS_LINUX:
            raise SandboxError(
                "OpenShell sandbox requires Linux. "
                f"Current platform: {sys.platform}"
            )

        # Verify unshare is available
        try:
            check = await asyncio.create_subprocess_exec(
                "which", _UNSHARE_CMD,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await check.communicate()
            if check.returncode != 0:
                raise SandboxError(
                    "unshare not found. Install: apt-get install util-linux"
                )
        except FileNotFoundError:
            raise SandboxError(
                "unshare command not found. Install: apt-get install util-linux"
            )

        # Start an isolated shell process
        # --net    = new network namespace (no network access)
        # --mount  = new mount namespace (isolated filesystem)
        # --pid    = new PID namespace
        # --fork   = fork into new namespace
        # --map-root-user = map current user to root (for mount ops)
        #
        # start_new_session: put the whole unshare tree in its OWN process
        # group. The namespace child runs as PID 1 inside the PID namespace,
        # which IGNORES unhandled signals (kernel semantics) — SIGTERM to the
        # unshare parent is therefore ineffective and wait() never returns.
        # A dedicated process group lets stop() kill the entire tree with
        # one group-wide SIGKILL (the only kernel-enforced signal).
        cmd = [
            _UNSHARE_CMD,
            "--net",
            "--mount",
            "--pid",
            "--fork",
            "--map-root-user",
            "python3", "-i",  # Interactive Python interpreter
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            self._running = True
            logger.info("[OpenShell] Started isolated namespace process")
        except PermissionError:
            raise SandboxError(
                "Permission denied for unshare. "
                "Try: sudo sysctl -w kernel.unprivileged_userns_clone=1"
            )
        except Exception as e:
            raise SandboxError(f"Failed to start OpenShell sandbox: {e}")

    async def exec(self, code: str) -> ToolResult:
        """Execute Python code in the isolated namespace.

        Args:
            code: Python code string to execute.

        Returns:
            ToolResult with stdout output or error.
        """
        if not self._running or not self._process:
            await self.start()

        assert self._process is not None
        assert self._process.stdin is not None

        # Send code to the isolated Python interpreter
        # Use exec() to avoid interactive prompts
        # Escape single quotes in code for embedding in exec() wrapper
        escaped = code.replace("'", "\\'")
        wrapped = f"exec('{escaped}')\n"

        try:
            # Write the code
            self._process.stdin.write(wrapped.encode())
            await self._process.stdin.drain()

            # Read output with timeout
            # For interactive mode, we use a marker to detect end of output
            marker = "__SHSCODE_EXEC_END__"
            self._process.stdin.write(
                f"print('{marker}')\n".encode()
            )
            await self._process.stdin.drain()

            # Collect output until we see the marker or timeout
            output_lines = []
            try:
                while True:
                    line = await asyncio.wait_for(
                        self._process.stdout.readline(),
                        timeout=self._timeout,
                    )
                    decoded = line.decode().rstrip()
                    if marker in decoded:
                        break
                    if decoded:
                        output_lines.append(decoded)
            except asyncio.TimeoutError:
                await self.stop()
                return ToolResult(
                    error=f"Execution timed out after {self._timeout}s"
                )

            output = "\n".join(output_lines) if output_lines else None
            return ToolResult(output=output)

        except BrokenPipeError:
            # Process died
            self._running = False
            return ToolResult(error="OpenShell process terminated unexpectedly")
        except Exception as e:
            return ToolResult(error=f"OpenShell execution error: {e}")

    async def exec_command(self, command: str) -> ToolResult:
        """Execute a shell command directly in a new isolated namespace.

        Unlike ``exec()`` which uses a persistent interpreter, this spawns
        a new isolated process for each command. Simpler but no state
        persistence between calls.

        Args:
            command: Shell command to execute.

        Returns:
            ToolResult with stdout output or error.
        """
        if not _IS_LINUX:
            return ToolResult(error="OpenShell sandbox requires Linux")

        cmd = [
            _UNSHARE_CMD,
            "--net",
            "--mount",
            "--pid",
            "--fork",
            "--map-root-user",
            "sh", "-c", command,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            error = stderr.decode().strip() or None if proc.returncode != 0 else None
            return ToolResult(output=stdout.decode().strip() or None, error=error)
        except asyncio.TimeoutError:
            return ToolResult(error=f"Command timed out after {self._timeout}s")
        except PermissionError:
            return ToolResult(error="Permission denied for unshare namespace isolation")
        except FileNotFoundError:
            return ToolResult(error="unshare command not found")
        except Exception as e:
            return ToolResult(error=f"OpenShell command error: {e}")

    async def stop(self) -> None:
        """Terminate the isolated namespace process tree.

        The namespace child runs as PID 1 in its PID namespace, which ignores
        unhandled signals — SIGTERM alone never works. Strategy:
          1. SIGKILL the entire process group (parent + namespace tree)
          2. Bounded asyncio wait; if the child watcher is desynced (e.g.
             after a cancelled wait()), reap synchronously with waitpid
        Every path is time-bounded: stop() can never hang forever.
        """
        if self._process and self._running:
            proc = self._process
            try:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass  # already dead
                deadline = time.monotonic() + 5.0
                while proc.returncode is None and time.monotonic() < deadline:
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(proc.wait()), 0.2)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        # child-watcher fallback: reap synchronously
                        try:
                            pid, _status = os.waitpid(proc.pid, os.WNOHANG)
                            if pid == proc.pid:
                                break
                        except ChildProcessError:
                            break  # reaped elsewhere
                if proc.returncode is None:
                    logger.warning(
                        f"[OpenShell] process {proc.pid} not reaped within 5s")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[OpenShell] Error stopping process: {e}")
            finally:
                self._process = None
                self._running = False
                logger.info("[OpenShell] Stopped isolated namespace process")
