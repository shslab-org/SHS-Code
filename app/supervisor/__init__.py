"""SHS Code supervisor lifecycle (FIX SPEC §10, v4.0.0 patch, no version bump).

Non-blocking/background execution for long-running supervisors:

  START → DETACH/BACKGROUND → MONITOR → WORK COMPLETES → STATUS DETECTED → CLEAN EXIT

Guarantees:
  - starting the supervisor never blocks the caller (double-fork detach)
  - duplicate supervisors are refused via PID-file guard (stale entries reclaimed)
  - status stays observable via atomic JSON status file (+ heartbeat)
  - completion/failure stays detectable via sentinel file
  - shutdown is clean (SIGTERM/SIGINT remove PID file, terminate child, write final status)
  - no orphaned worker child on supervisor exit (child process group killed)

The operator-owned scripts under ``/home/z/my-project/scripts/`` keep working
copies (``supervisor_fixed.py`` / ``launch_fixed.py`` / ``monitor_fix.sh``);
this package is the definitive in-repo implementation with unit tests.
"""
from app.supervisor.lifecycle import (
    SupervisorGuard,
    SupervisorStatus,
    acquire_guard,
    daemonize,
    install_signal_handlers,
    pid_alive,
    read_status,
    release_guard,
    write_status,
)

__all__ = [
    "SupervisorGuard",
    "SupervisorStatus",
    "acquire_guard",
    "daemonize",
    "install_signal_handlers",
    "pid_alive",
    "read_status",
    "release_guard",
    "write_status",
]
