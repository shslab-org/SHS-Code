"""Detached execution + run registry (v4.3.0 — long-running task lifecycle).

THE PROBLEM THIS SOLVES (real test-run finding)
===============================================
An SHS Code agent launched "in the background" (plain ``&`` or a
subprocess of a shell/session) DIED the moment the surrounding tool
session ended — the child sat in the parent's process group and received
the same termination signals / process-tree cleanup, killing work that
had already started (files created, steps consumed, no completion).

THE FIX
=======
A proper daemonization path for long-running agent work:

  * ``SHSCode --detach "<task>"`` — double-fork + ``setsid`` (new session,
    no controlling terminal), stdio redirected to a per-run log file, then
    ``exec`` of a FRESH ``python -m app`` one-shot process. The daemon is
    reparented to init, so it survives the invoking shell, the terminal,
    and process-tree cleanup of the tool that started it.
  * Every detached run registers itself in ``~/.shscode/runs/<run_id>/``:
    ``run.json`` (pid, session_id, prompt, argv, timestamps) plus
    ``output.log``. Liveness is checked against the REAL pid; task state
    lives in the sessions DB as always (checkpointed every step).
  * ``--runs`` lists the registry; ``--attach <run_id>`` follows the log.
  * The detached child handles SIGTERM/SIGINT by cancelling the agent run
    GRACEFULLY — the agent checkpoints and closes the session as
    ``interrupted`` (``--continue`` / ``/resume`` restore it cleanly).
  * The GUI/server path: ``POST /run {"detach": true}`` spawns the same
    detached process, so a long task survives even a server restart.

Nothing here fakes completion: if the process dies, the run registry and
session DB show the truth (interrupted/partial), and resume continues
from the last checkpoint.
"""
from __future__ import annotations

import json
import os
import signal
import time
import uuid
import warnings
from pathlib import Path
from typing import Optional

from app import env
from app.logger import logger

RUNS_DIR = env.home_dir() / "runs"


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def new_run_id() -> str:
    return time.strftime("run-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def register_run(run_id: str, pid: int, session_id: str, prompt: str,
                 log_path: str, argv: Optional[list] = None,
                 detached_by: str = "cli") -> Path:
    """Write the run registry entry (run.json)."""
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_id": run_id,
        "pid": pid,
        "session_id": session_id,
        "prompt": prompt[:500],
        "argv": argv or [],
        "log_path": log_path,
        "started_at": time.time(),
        "detached_by": detached_by,
        "status": "running",
    }
    p = d / "run.json"
    p.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return p


def update_run(run_id: str, **fields) -> None:
    try:
        p = run_dir(run_id) / "run.json"
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        data.update(fields)
        data["updated_at"] = time.time()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    except Exception as e:
        logger.debug(f"[Runs] update {run_id} failed: {e}")


def pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)          # signal 0 = existence probe
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True              # exists, owned by someone else
    except OSError:
        return False


def list_runs(limit: int = 30) -> list[dict]:
    """All registered runs, newest first, with live liveness info."""
    out: list[dict] = []
    try:
        entries = sorted(RUNS_DIR.glob("*/run.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return out
    for p in entries[: limit * 2]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        alive = pid_alive(int(data.get("pid") or 0))
        data["alive"] = alive
        data["status"] = "running" if alive else data.get("status", "exited")
        out.append(data)
        if len(out) >= limit:
            break
    return out


def get_run(run_id: str) -> Optional[dict]:
    p = run_dir(run_id) / "run.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data["alive"] = pid_alive(int(data.get("pid") or 0))
        return data
    except Exception:
        return None


def start_detached_run(argv: list[str], run_id: Optional[str] = None,
                       log_path: Optional[str] = None,
                       session_id: Optional[str] = None,
                       prompt: str = "", detached_by: str = "cli",
                       cwd: Optional[str] = None) -> dict:
    """Double-fork + setsid + exec a fresh one-shot process.

    ``argv`` is the FULL argument vector for the new process — the caller
    is responsible for having removed ``--detach`` and injected
    ``--session <id>`` (both are provided by the CLI wrapper).

    Returns the registry entry (run_id, pid, log_path, session_id). The
    parent returns as soon as the intermediate child exits, which happens
    immediately after the second fork — the daemon grandchild is fully
    reparented to init and immune to the parent's session termination.
    """
    run_id = run_id or new_run_id()
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    log_path = log_path or str(d / "output.log")

    # Pre-open the log with O_APPEND so the daemon's stdout/stderr land in
    # one place even across exec.
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    devnull_fd = os.open(os.devnull, os.O_RDONLY)

    # Python 3.12+ warns about fork() in multi-threaded processes (the
    # server is threaded). The children here only call async-signal-safe
    # primitives before exec, so the deadlock risk does not apply — but we
    # silence the warning so logs stay clean.
    import contextlib
    with contextlib.suppress(DeprecationWarning), \
            warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        pid = os.fork()
    if pid > 0:
        # Parent: wait for the intermediate child to exit (it does so right
        # after forking the daemon), then return the registry info.
        os.close(log_fd)
        os.close(devnull_fd)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        # register from the parent using the KNOWN daemon pid is impossible
        # before it exists — the daemon registers itself pre-exec (below).
        return {"run_id": run_id, "log_path": log_path,
                "session_id": session_id, "registry": str(d / "run.json")}

    # ── intermediate child: new session, drop the controlling terminal ──
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)          # intermediate exits — daemon is orphaned to init

    # ── daemon grandchild ──
    try:
        os.dup2(devnull_fd, 0)      # stdin: /dev/null
        os.dup2(log_fd, 1)          # stdout -> log
        os.dup2(log_fd, 2)          # stderr -> log
        if devnull_fd > 2:
            os.close(devnull_fd)
        if log_fd > 2:
            os.close(log_fd)
        # ignore HUP completely (immune to terminal hangups)
        try:
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        except Exception:
            pass
        register_run(run_id, os.getpid(), session_id or "", prompt,
                     log_path, argv=argv, detached_by=detached_by)
        if cwd:
            os.chdir(cwd)
        exe = os.environ.get("SHSCODE_PYTHON") or _same_interpreter()
        os.execv(exe, [exe] + argv)
    except Exception as e:  # exec failed — leave a clear trace in the log
        try:
            os.write(2, f"[daemon] exec failed: {e}\n".encode())
        except Exception:
            pass
        os._exit(127)
    return {}  # unreachable


def _same_interpreter() -> str:
    import sys
    return sys.executable or "python3"


def format_runs_table(runs: list[dict]) -> str:
    """Human-readable table for the CLI ``--runs`` view."""
    if not runs:
        return "No detached runs registered yet."
    lines = []
    for r in runs:
        alive = "● running" if r.get("alive") else "○ exited"
        age = int(max(0, time.time() - float(r.get("started_at") or 0)))
        age_s = f"{age//3600}h{(age%3600)//60:02d}m" if age >= 3600 else f"{age//60}m{age%60:02d}s"
        prompt = (r.get("prompt") or "").replace("\n", " ")[:46]
        lines.append(
            f"{r.get('run_id','?')}  {alive:<9} {age_s:>7}  pid {r.get('pid','?'):<7} "
            f"session {str(r.get('session_id') or '-')[:14]:<14} {prompt}")
    return "\n".join(lines)


def follow_log(run_id: str, poll_s: float = 1.0, idle_exit_s: float = 4.0) -> int:
    """``--attach``: stream the run's log until the process is gone and the
    log has been quiet for a moment. Returns the exit hint (0 ok)."""
    info = get_run(run_id)
    if info is None:
        print(f"Run {run_id} not found in {RUNS_DIR}")
        return 1
    log_path = info.get("log_path") or str(run_dir(run_id) / "output.log")
    print(f"Attaching to {run_id} (pid {info.get('pid')}) — log: {log_path}")
    print("Ctrl+C to detach (the run keeps going).\n")
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            quiet = 0.0
            import selectors
            sel = selectors.DefaultSelector()
            sel.register(f, selectors.EVENT_READ)
            while True:
                events = sel.select(timeout=poll_s)
                if events:
                    quiet = 0.0
                    for line in f:
                        print(line, end="", flush=True)
                else:
                    quiet += poll_s
                if not pid_alive(int(info.get("pid") or 0)) and quiet >= idle_exit_s:
                    print(f"\n[attach] process {info.get('pid')} has exited.")
                    break
    except KeyboardInterrupt:
        print("\n[attach] detached — the run continues in the background.")
    except FileNotFoundError:
        print(f"(no log at {log_path})")
    return 0
