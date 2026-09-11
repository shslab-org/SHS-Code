"""Supervisor lifecycle primitives (FIX SPEC §10, v4.0.0 patch, no version bump).

Implements START → DETACH/BACKGROUND → MONITOR → WORK COMPLETES →
STATUS DETECTED → CLEAN EXIT without blocking the caller.

Design notes vs the operator scripts (``supervisor_v4.py`` /
``supervisor_fix.py`` / ``launch_shs_v4.py``):
  - old scripts call ``daemonize()`` unconditionally at import/run time,
    so even ``--help``-style invocations detach; here detach is explicit.
  - old ``duplicate_guard()`` writes the PID file AFTER forking but never
    removes stale entries robustly and never records observable status;
    here the guard is atomic-ish (O_EXCL create), reaps stale PIDs, and
    pairs with a JSON status file carrying heartbeat + run counts.
  - old scripts have no signal handling: SIGTERM leaves the PID file
    behind and orphans the worker child; here SIGTERM/SIGINT terminate
    the child process group and write a final status.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SupervisorStatus:
    state: str = "starting"  # starting|running|done|error|stopped
    pid: int = 0
    runs: int = 0
    last_rc: Optional[int] = None
    last_event: str = ""
    heartbeat: float = 0.0
    done_sentinel: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SupervisorGuard:
    pid_file: str
    pid: int
    fd: int = -1  # reserved for future flock-based guard


def pid_alive(pid: int) -> bool:
    """True when a process with ``pid`` exists (SIG 0 probe)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def daemonize(log_path: Optional[str] = None) -> int:
    """Double-fork detach; returns 0 in the detached child.

    Raises SystemExit(0) in every parent so callers never continue twice.
    When ``log_path`` is given, stdout/stderr are appended there.
    """
    if os.fork() > 0:
        raise SystemExit(0)
    os.setsid()
    if os.fork() > 0:
        raise SystemExit(0)
    try:
        fd = os.open(os.devnull, os.O_RDONLY)
        os.dup2(fd, 0)
        if hasattr(os, "close"):
            try:
                if fd > 2:
                    os.close(fd)
            except OSError:
                pass
    except OSError:
        pass
    if log_path:
        try:
            out = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.dup2(out, 1)
            os.dup2(out, 2)
            if out > 2:
                os.close(out)
        except OSError:
            pass
    return 0


def acquire_guard(pid_file: str) -> SupervisorGuard:
    """Claim the singleton guard; refuse when a live supervisor holds it.

    Stale PID files (dead pid / unparsable content) are reclaimed.
    Uses O_EXCL create for atomicity against concurrent starters.
    """
    try:
        fd = os.open(pid_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return SupervisorGuard(pid_file=pid_file, pid=os.getpid())
    except FileExistsError:
        pass
    # PID file exists — inspect current holder.
    try:
        with open(pid_file) as f:
            old = int(f.read().strip())
    except (ValueError, OSError):
        # Unparsable: reclaim.
        try:
            os.remove(pid_file)
        except OSError:
            pass
        return acquire_guard(pid_file)
    if pid_alive(old):
        # Any live holder — including this same process — blocks a second
        # supervisor. Same-process re-acquire must also refuse (no duplicates).
        raise RuntimeError(f"supervisor already running as pid {old}")
    # Stale holder: reclaim and retry once.
    try:
        os.remove(pid_file)
    except OSError:
        pass
    fd = os.open(pid_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    return SupervisorGuard(pid_file=pid_file, pid=os.getpid())


def release_guard(guard: SupervisorGuard) -> None:
    """Release the guard; only the owner removes the PID file."""
    try:
        with open(guard.pid_file) as f:
            cur = int(f.read().strip())
        if cur == guard.pid:
            os.remove(guard.pid_file)
    except (ValueError, OSError):
        pass


def write_status(status_path: str, status: SupervisorStatus) -> None:
    """Atomically write the JSON status file (tmp + rename)."""
    status.heartbeat = time.time()
    tmp = status_path + f".tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(asdict(status), f)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, status_path)


def read_status(status_path: str, max_age_s: float = 120.0) -> Optional[SupervisorStatus]:
    """Read status; None when missing/corrupt. ``extra['stale']`` flags old heartbeat."""
    try:
        with open(status_path) as f:
            data = json.load(f)
        st = SupervisorStatus(
            state=str(data.get("state", "")),
            pid=int(data.get("pid", 0) or 0),
            runs=int(data.get("runs", 0) or 0),
            last_rc=data.get("last_rc"),
            last_event=str(data.get("last_event", "")),
            heartbeat=float(data.get("heartbeat", 0.0) or 0.0),
            done_sentinel=str(data.get("done_sentinel", "")),
            extra=dict(data.get("extra", {}) or {}),
        )
        if max_age_s > 0 and time.time() - st.heartbeat > max_age_s:
            st.extra["stale"] = True
        return st
    except (OSError, ValueError, TypeError, KeyError):
        return None


def install_signal_handlers(
    guard: SupervisorGuard,
    status_path: str,
    status: SupervisorStatus,
    child: Optional[subprocess.Popen] = None,
) -> None:
    """Install SIGTERM/SIGINT handlers for clean shutdown.

    On signal: terminate the worker child process group (no orphans),
    write final ``stopped`` status, release the PID guard, exit 143/130.
    """

    def _shutdown(signum: int, _frame: Any) -> None:
        if child is not None and child.poll() is None:
            try:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    child.terminate()
                try:
                    child.wait(timeout=10)
                except Exception:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except (OSError, ProcessLookupError):
                        try:
                            child.kill()
                        except Exception:
                            pass
            except Exception:
                pass
        status.state = "stopped"
        status.last_event = f"signal {signum}"
        try:
            write_status(status_path, status)
        except OSError:
            pass
        release_guard(guard)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
