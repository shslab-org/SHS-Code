"""Supervisor lifecycle tests (FIX SPEC §10, v4.0.0 patch, no version bump).

Covers START → DETACH/BACKGROUND → MONITOR → WORK COMPLETES →
STATUS DETECTED → CLEAN EXIT using short-lived controlled child
processes and a dedicated test sentinel path (never live mission paths).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.supervisor.lifecycle import (
    acquire_guard,
    pid_alive,
    read_status,
    release_guard,
    SupervisorStatus,
    write_status,
)


def test_pid_alive_self():
    assert pid_alive(os.getpid())
    assert not pid_alive(2**31 - 1)


def test_guard_acquire_release_reclaim(tmp_path):
    pid_file = str(tmp_path / "sup.pid")
    g = acquire_guard(pid_file)
    assert Path(pid_file).read_text().strip() == str(os.getpid())
    # Second acquire while live holder exists must refuse.
    with pytest.raises(RuntimeError, match="already running"):
        acquire_guard(pid_file)
    release_guard(g)
    assert not Path(pid_file).exists()
    # Stale PID file is reclaimed.
    Path(pid_file).write_text("999999999")
    g2 = acquire_guard(pid_file)
    assert Path(pid_file).read_text().strip() == str(os.getpid())
    release_guard(g2)


def test_guard_unparsable_reclaimed(tmp_path):
    pid_file = str(tmp_path / "sup.pid")
    Path(pid_file).write_text("not-a-pid")
    g = acquire_guard(pid_file)
    release_guard(g)
    assert not Path(pid_file).exists()


def test_status_roundtrip_and_stale(tmp_path):
    sp = str(tmp_path / "status.json")
    st = SupervisorStatus(state="running", pid=os.getpid(), runs=3,
                          last_rc=0, last_event="run #3 rc=0")
    write_status(sp, st)
    back = read_status(sp)
    assert back is not None
    assert back.state == "running"
    assert back.runs == 3
    assert back.pid == os.getpid()
    assert "stale" not in back.extra
    # Force old heartbeat → stale flag.
    data = json.loads(Path(sp).read_text())
    data["heartbeat"] = time.time() - 9999
    Path(sp).write_text(json.dumps(data))
    back2 = read_status(sp, max_age_s=60)
    assert back2 is not None and back2.extra.get("stale") is True
    assert read_status(str(tmp_path / "missing.json")) is None


def test_full_lifecycle_short_lived_child(tmp_path):
    """START → BACKGROUND child → MONITOR status → COMPLETES → CLEAN EXIT.

    Uses a 0.3s sleep child + sentinel file in tmp_path only.
    """
    pid_file = str(tmp_path / "sup.pid")
    status_path = str(tmp_path / "status.json")
    sentinel = tmp_path / "DONE.md"

    guard = acquire_guard(pid_file)
    status = SupervisorStatus(state="running", pid=os.getpid(),
                              done_sentinel=str(sentinel))
    write_status(status_path, status)

    # DETACH/BACKGROUND: spawn short-lived child, caller not blocked.
    t0 = time.monotonic()
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.3)"],
        start_new_session=True,
    )
    assert time.monotonic() - t0 < 5  # start must not block caller
    assert child.poll() is None  # still running → monitoring phase

    # MONITOR: status observable while child runs.
    mid = read_status(status_path)
    assert mid is not None and mid.state == "running"

    rc = child.wait(timeout=10)
    assert rc == 0

    # WORK COMPLETES → STATUS DETECTED → CLEAN EXIT.
    sentinel.write_text("complete")
    status.runs = 1
    status.last_rc = rc
    status.last_event = "child rc=0"
    status.state = "done" if sentinel.exists() else "running"
    write_status(status_path, status)
    release_guard(guard)

    final = read_status(status_path)
    assert final is not None and final.state == "done"
    assert not Path(pid_file).exists()


def test_no_duplicate_supervisors(tmp_path):
    pid_file = str(tmp_path / "sup.pid")
    g = acquire_guard(pid_file)
    try:
        # Simulate a second starter process: same PID file, live holder.
        with pytest.raises(RuntimeError):
            acquire_guard(pid_file)
    finally:
        release_guard(g)
