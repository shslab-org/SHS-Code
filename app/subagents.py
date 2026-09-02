from __future__ import annotations

"""
SHS Code — Subagent State Persistence (spec §26)
==================================================
Every subagent (delegate tool spawns) gets persistent task identity in
journal.db:

  subagents(task_id, sub_id, role, goal, parent_id, status, output,
            files_changed, error, created_at, updated_at)

A parent agent can recover subagent progress after interruption:
  list_subagents(task_id) shows status of every spawned subagent
  incomplete ones can be re-spawned with their original goal.

Used by the delegate tool (record start/finish) and /status.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from app.logger import logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subagents (
    sub_id       TEXT PRIMARY KEY,
    task_id      TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'worker',
    goal         TEXT NOT NULL,
    parent_id    TEXT,
    status       TEXT NOT NULL DEFAULT 'running',
    output       TEXT NOT NULL DEFAULT '',
    files_changed TEXT NOT NULL DEFAULT '[]',
    error        TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subagents_task ON subagents(task_id, status);
"""

# statuses: running | completed | failed | interrupted


def ensure_schema(journal) -> None:
    """Create the subagents table if missing (idempotent)."""
    try:
        if journal is None:
            return
        with journal._rl:
            journal._connection().executescript(_SCHEMA)
            journal._connection().commit()
    except Exception as e:
        logger.debug(f"[Subagents] schema init failed: {e}")


async def start_subagent(journal, task_id: str, goal: str, role: str = "worker",
                         parent_id: str = "") -> str:
    ensure_schema(journal)
    sub_id = f"sub-{uuid.uuid4().hex[:8]}"
    now = time.time()
    await journal.exec_sql(
        "INSERT INTO subagents (sub_id, task_id, role, goal, parent_id, status,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (sub_id, task_id, role, goal[:1000], parent_id or task_id,
         "running", now, now))
    await journal._log(task_id, "subagent_start", None,
                       {"sub_id": sub_id, "role": role, "goal": goal[:200]})
    from app.activity import emit
    emit("subagent_start", sub_id=sub_id, role=role)
    return sub_id


async def finish_subagent(journal, task_id: str, sub_id: str,
                          output: str = "", error: str = "",
                          files_changed: Optional[List[str]] = None) -> None:
    ensure_schema(journal)
    status = "failed" if error else "completed"
    await journal.exec_sql(
        "UPDATE subagents SET status=?, output=?, error=?, files_changed=?,"
        " updated_at=? WHERE sub_id=?",
        (status, (output or "")[:4000], (error or "")[:1500],
         json.dumps(files_changed or []), time.time(), sub_id))
    await journal._log(task_id, "subagent_end", None,
                       {"sub_id": sub_id, "status": status,
                        "output_preview": (output or "")[:200]})
    from app.activity import emit
    emit("subagent_end", sub_id=sub_id, status=status)


async def mark_interrupted_subagents(journal, task_id: str) -> int:
    """On resume: running subagents from a dead process become 'interrupted'."""
    ensure_schema(journal)
    rows = await journal.query_sql(
        "SELECT sub_id FROM subagents WHERE task_id=? AND status='running'",
        (task_id,))
    for r in rows:
        await journal.exec_sql(
            "UPDATE subagents SET status='interrupted', updated_at=? WHERE sub_id=?",
            (time.time(), r["sub_id"]))
    return len(rows)


async def list_subagents(journal, task_id: str) -> List[Dict[str, Any]]:
    ensure_schema(journal)
    rows = await journal.query_sql(
        "SELECT * FROM subagents WHERE task_id=? ORDER BY created_at", (task_id,))
    for r in rows:
        r["files_changed"] = json.loads(r.get("files_changed") or "[]")
    return rows


async def incomplete_subagents(journal, task_id: str) -> List[Dict[str, Any]]:
    rows = await list_subagents(journal, task_id)
    return [r for r in rows if r["status"] in ("running", "interrupted", "failed")]


def render_subagents(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "(no subagents)"
    marks = {"completed": "✓", "running": "▶", "failed": "✗",
             "interrupted": "⏸"}
    lines = [f"SUBAGENTS ({len(rows)}):"]
    for r in rows:
        mark = marks.get(r["status"], "·")
        out = (r.get("output") or "").strip().replace("\n", " ")[:60]
        lines.append(f"  {mark} {r['sub_id']} [{r.get('role', 'worker')}] "
                     f"{r['status']:<12} {r.get('goal', '')[:56]}"
                     + (f" → {out}" if out else ""))
        if r.get("error"):
            lines.append(f"      error: {r['error'][:120]}")
    return "\n".join(lines)
