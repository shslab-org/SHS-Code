from __future__ import annotations

r"""
Shell — persistent async shell session, cross-platform.

Platforms:
  Linux   → bash --norc --noprofile
  macOS   → bash --norc --noprofile  (or zsh if bash absent)
  Windows → PowerShell -NoProfile -NonInteractive
  Termux  → bash (no --norc needed, profile is fine)

Runtime philosophy: TASK-COMPLETE, NOT TIME-BOXED.
  No DEFAULT timeout. No MAX cap.
  Pass timeout=None (or omit) → runs until natural completion.
  Pass timeout=N   → killed after exactly N seconds.

Blocked (hard deny — OS-destroying only):
  Linux/Mac: rm -rf /  fork bombs  dd to block dev  mkfs  kill -9 -1
  Windows:   rd /s /q C:\  format C:  del /f /s /q C:\Windows\*
"""

import asyncio
import atexit
import re
import shutil
import sys
import weakref
from typing import Any, Optional

from app.logger import logger
from app.schema import ToolResult
from app.tool.base import BaseTool


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"
IS_TERMUX  = not IS_WINDOWS and shutil.which("termux-info") is not None


def _shell_cmd() -> str:
    if IS_WINDOWS:
        return "powershell.exe -NoProfile -NonInteractive -Command -"
    bash = shutil.which("bash")
    if bash:
        return f"{bash} --norc --noprofile"
    zsh = shutil.which("zsh")
    if zsh:
        return zsh
    return "sh"


def _sentinel_cmd(sentinel: str) -> str:
    if IS_WINDOWS:
        return f'Write-Host "{sentinel}"'
    return f"echo {sentinel}"


def _exit_cmd() -> str:
    if IS_WINDOWS:
        return r'Write-Host "__SHS_EXIT__:$LASTEXITCODE"'
    return 'echo "__SHS_EXIT__:$?"'


def _wrap(command: str, sentinel: str) -> str:
    if IS_WINDOWS:
        return (
            f"{command}\n"
            f"{_exit_cmd()}\n"
            f"{_sentinel_cmd(sentinel)}\n"
        )
    # SHS Code FIX (heredoc hang): the old one-liner `(cmd); echo ...` broke
    # ANY command containing a heredoc — `PY);` is not a valid heredoc
    # terminator, so the shell never closed it, consumed the rest of stdin
    # and the tool waited until its deadline. Newline-separated lines keep
    # the subshell isolation (cd does not leak) AND keep heredoc/multiline
    # terminators pure.
    return (
        f"(\n{command}\n)\n"
        f"{_exit_cmd()}\n"
        f"{_sentinel_cmd(sentinel)}\n"
    )


# ---------------------------------------------------------------------------
# Catastrophic patterns — the ONLY restriction, per platform
# ---------------------------------------------------------------------------

_CATASTROPHIC_UNIX = [
    r"rm\s+-[rRf]+\s+/\s*$",
    r"rm\s+-[rRf]+\s+/\*",
    r"rm\s+--no-preserve-root",
    r":\(\)\s*\{.*:\|:.*\}",                       # fork bomb
    r"dd\s+if=/dev/zero\s+of=/dev/(s|h|v|xv)d\b",
    r">\s*/dev/(s|h|v|xv)d[a-z]\b",
    r"mkfs\.",
    r"wipefs\s",
    r"kill\s+-9\s+-1\b",
    r"killall\s+-9\b",
    r"shred\s+.*/(bin|sbin|lib|usr|boot)/",
]

_CATASTROPHIC_WINDOWS = [
    r"rd\s+/[sS]\s+/[qQ]\s+[Cc]:\\?\s*$",         # rd /s /q C:\
    r"del\s+/[fF]\s+/[sS]\s+/[qQ]\s+[Cc]:\\[Ww]indows",
    r"format\s+[Cc]:",                              # format C:
    r"rmdir\s+/[sS]\s+[Cc]:\\?\s*$",
    r"Remove-Item\s+-Recurse\s+-Force\s+[Cc]:\\?\s*$",
    r"Remove-Item\s+.*-Recurse.*[Cc]:\\[Ww]indows",
]

_PATTERNS = _CATASTROPHIC_WINDOWS if IS_WINDOWS else _CATASTROPHIC_UNIX


def _is_catastrophic(command: str) -> Optional[str]:
    for p in _PATTERNS:
        if re.search(p, command, re.IGNORECASE | re.DOTALL):
            return p
    return None


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class Bash(BaseTool):
    name = "bash"
    description = (
        "Execute shell commands in a persistent session. "
        f"Platform: {'Windows (PowerShell)' if IS_WINDOWS else 'Linux/macOS/Termux (bash)'}. "
        "Runs until completion — no artificial time limit. "
        "Pass timeout=N (seconds) to set an explicit deadline. "
        "Full output always returned — no truncation. "
        "Environment and working directory persist across calls. "
        "Only OS-destroying commands are blocked."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Shell command to run. "
                    f"{'PowerShell syntax on Windows.' if IS_WINDOWS else 'Bash syntax on Linux/macOS/Termux.'}"
                ),
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Optional. Kill after this many seconds. "
                    "Omit to run until natural completion — 2min tasks run 2min, "
                    "3h jobs run 3h. Only set if you need a hard deadline."
                ),
            },
        },
        "required": ["command"],
    }

    # v3.1 FIX (atexit leak): every Bash instance registered a STRONG-ref
    # atexit handler that is never unregistered — per-request agents pinned
    # their Bash objects in the atexit registry forever (unbounded memory
    # growth in server/cron processes, thousands of handlers at exit). One
    # module-level handler now tracks instances WEAKLY.
    _INSTANCES: "weakref.WeakSet[object]" = weakref.WeakSet()

    def __init__(self) -> None:
        self._process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        Bash._INSTANCES.add(self)

    @staticmethod
    def _sync_kill_all() -> None:
        """Synchronous atexit handler — kill ALL orphaned bash subprocesses
        (module-level, weakly referenced; registered exactly once)."""
        for inst in list(Bash._INSTANCES):
            proc = getattr(inst, "_process", None)
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
                # v3.1: reap to avoid a zombie at exit and close transports
                try:
                    transport = getattr(proc, "_transport", None)
                    if transport is not None:
                        transport.close()
                except Exception:
                    pass

    async def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        **_: Any,
    ) -> ToolResult:
        bad = _is_catastrophic(command)
        if bad:
            return ToolResult(
                error=(
                    f"BLOCKED — catastrophic OS-destroying pattern: `{bad}`\n"
                    "This is the ONLY category of blocked commands. "
                    "All other system operations are fully permitted."
                )
            )
        async with self._lock:
            return await self._run(command, timeout)

    async def _run(self, command: str, timeout: Optional[int]) -> ToolResult:
        sentinel = "__MC_DONE_9742__"
        wrapped  = _wrap(command, sentinel).encode()

        try:
            proc = await self._ensure_process()
            assert proc.stdin is not None and proc.stdout is not None

            proc.stdin.write(wrapped)
            await proc.stdin.drain()

            lines: list[str] = []
            exit_code: Optional[int] = None

            async def _read() -> None:
                nonlocal exit_code
                while True:
                    raw  = await proc.stdout.readline()
                    # SHS Code FIX (EOF busy-loop): when the persistent shell
                    # dies (agent killed it, OOM, crash), readline() returns
                    # b"" forever and each await completes synchronously —
                    # the loop never yields, starving the event loop (no
                    # timeouts, no cancellation, frozen activity feed).
                    if not raw:
                        raise BrokenPipeError("shell EOF")
                    line = raw.decode(errors="replace").rstrip("\r\n")
                    if line.strip() == sentinel:
                        break
                    if line.startswith("__SHS_EXIT__:"):
                        try:
                            exit_code = int(line[len("__SHS_EXIT__:"):].strip())
                        except ValueError:
                            pass
                        continue
                    lines.append(line)

            await asyncio.wait_for(_read(), timeout=timeout)
            output = "\n".join(lines)

            if exit_code is not None and exit_code != 0:
                return ToolResult(
                    output=output or None,
                    error=(
                        f"Command exited with code {exit_code}.\n"
                        f"Output:\n{output}\n\n"
                        "Review the error and adjust your command."
                    ),
                )
            return ToolResult(output=output or "(command completed, no output)")

        except asyncio.TimeoutError:
            logger.warning(f"[bash] Deadline reached after {timeout}s.")
            await self._reset_process()
            return ToolResult(
                error=(
                    f"Deadline reached after {timeout}s. Session reset. "
                    "Omit timeout to run until done, or use background execution."
                )
            )
        except BrokenPipeError:
            await self._reset_process()
            return ToolResult(error="Shell session died. Restarted — retry.")
        except asyncio.CancelledError:
            # v3.1 FIX: a cancelled read left the command RUNNING in the
            # persistent shell — its buffered output was then misattributed
            # to the NEXT command (output mixing) and the shell stayed
            # mid-command. Reset, then re-raise so cancellation propagates.
            await self._reset_process()
            raise
        except Exception as e:
            # v3.1 FIX: no reset here left the session broken — the next
            # call's sentinel never appeared (hang until timeout).
            await self._reset_process()
            return ToolResult(error=f"Shell error: {e}")

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._process is None or self._process.returncode is not None:
            self._process = await asyncio.create_subprocess_shell(
                _shell_cmd(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        return self._process

    async def _reset_process(self) -> None:
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        # SHS Code FIX (one-shot leak regression): terminate/wait reaps the
        # child process but does NOT close the pipe transports. The stdin
        # writer transport stayed open, was finalized by GC AFTER the event
        # loop closed, and printed "Event loop is closed" on every one-shot
        # exit. Close the transport explicitly while the loop is still alive.
        if self._process is not None:
            transport = getattr(self._process, "_transport", None)
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass
        self._process = None

    async def cleanup(self) -> None:
        await self._reset_process()


# v3.1: single module-level atexit handler (weak instance tracking) —
# registered exactly once when the module loads.
atexit.register(Bash._sync_kill_all)
