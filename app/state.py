from __future__ import annotations

"""
SHS Code — Persistent Task Journal & State Layer
================================================
(spec §5, §6, §7, §8, §9, §33, §36, §43)

Provider-independent persistent state that survives:
  process exit, terminal close, restart, provider change, model change,
  rate-limit waits, network failure, context compaction, interruption.

Layers (spec §39):
  MEMORY      -> LongTermMemory (SQLite FTS, recalled into prompts)
  CONTEXT     -> agent ShortTermMemory snapshots (checkpointed here)
  TASK STATE  -> this journal (progress, next action, files changed)
  PROJECT STATE -> actual filesystem, mirrored as records here

Storage:
  ~/.shscode/state/journal.db   (SQLite, WAL) — tasks + event log
  ~/.shscode/state/checkpoints/<task_id>.json (atomic os.replace) — memory snapshots

Atomicity (spec §43): checkpoints are written to a temp file then
os.replace()d — a crash mid-write can never corrupt the previous snapshot.

Integration points (already wired):
  - BaseAgent.run()        -> task_start / task_complete / task_error
  - ToolCallAgent._execute_with_retry -> record_action (success/failure),
                              record_file_change, record_command, checkpoint
  - CLI /status /tasks /resume /checkpoint /history read from here
  - LLM rate-limit waits leave state untouched by design (spec §19)

API is fully async (asyncio.to_thread for the SQLite work) and never
raises into the agent loop — journal failures are logged and swallowed
so persistence can never break task execution.
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger
from app import env

_HOME = env.home_dir()
STATE_DIR = _HOME / "state"
CHECKPOINT_DIR = STATE_DIR / "checkpoints"
DB_PATH = STATE_DIR / "journal.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,
    goal         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'in_progress',
    session_id   TEXT,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    progress     TEXT NOT NULL DEFAULT '{"completed":[],"in_progress":[],"pending":[]}',
    current_step TEXT,
    last_success TEXT,
    last_error  TEXT,
    next_action  TEXT,
    files_changed TEXT NOT NULL DEFAULT '[]',
    commands     TEXT NOT NULL DEFAULT '[]',
    step_count   INTEGER NOT NULL DEFAULT 0,
    tool_calls   INTEGER NOT NULL DEFAULT 0,
    cwd          TEXT,
    provider     TEXT,
    model        TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  TEXT NOT NULL,
    ts       REAL NOT NULL,
    kind     TEXT NOT NULL,
    tool     TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_task ON journal(task_id, ts);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""

# statuses: queued | in_progress | paused | completed | failed | interrupted

# ── Phase 2 (spec §6-§9): Task DAG table + Work State 2.0 columns ──
_DAG_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_nodes (
    task_id     TEXT NOT NULL,
    node_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    priority    INTEGER NOT NULL DEFAULT 5,
    depends_on  TEXT NOT NULL DEFAULT '[]',
    files       TEXT NOT NULL DEFAULT '[]',
    notes       TEXT NOT NULL DEFAULT '',
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (task_id, node_id)
);
CREATE INDEX IF NOT EXISTS idx_task_nodes_task ON task_nodes(task_id, status);
"""

# Work State 2.0 (spec §9) — new columns added via idempotent migration
_WS2_COLUMNS = {
    "plan": "TEXT NOT NULL DEFAULT '[]'",           # TaskGraph snapshot
    "phase": "TEXT NOT NULL DEFAULT ''",            # current phase name
    "decisions": "TEXT NOT NULL DEFAULT '[]'",       # important decisions
    "test_results": "TEXT NOT NULL DEFAULT '[]'",   # verification results
    "recovery_actions": "TEXT NOT NULL DEFAULT '[]'",
    "blocked_reason": "TEXT",                      # human-dependency (spec §47)
    "verification": "TEXT NOT NULL DEFAULT '{}'",  # last verification outcome
}


class Journal:
    """Persistent task journal + checkpoint store. Singleton via get_journal()."""

    _instance: Optional["Journal"] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.checkpoint_dir = self.db_path.parent / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._rl = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        with self._rl:
            conn = self._connection()
            conn.executescript(_SCHEMA)
            conn.executescript(_DAG_SCHEMA)
            # Phase 2 migration: add Work State 2.0 columns if missing
            have = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            for col, ddl in _WS2_COLUMNS.items():
                if col not in have:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {ddl}")
            conn.commit()

    @classmethod
    def get(cls) -> "Journal":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def close(self) -> None:
        with self._rl:
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._rl:
            conn = self._connection()
            conn.execute(sql, params)
            conn.commit()

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._rl:
            conn = self._connection()
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    # Public typed-SQL surface (Phase 2: TaskGraph + planner use this
    # instead of reaching into private plumbing).
    async def exec_sql(self, sql: str, params: tuple = ()) -> None:
        await self._aexec(sql, params)

    async def query_sql(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        return await self._aquery(sql, params)

    async def _aexec(self, sql: str, params: tuple = ()) -> None:
        try:
            await asyncio.to_thread(self._exec, sql, params)
        except Exception as e:
            logger.error(f"[Journal] write failed: {e}")

    async def _aquery(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        try:
            return await asyncio.to_thread(self._query, sql, params)
        except Exception as e:
            logger.error(f"[Journal] read failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Task lifecycle (spec §7, §8)
    # ------------------------------------------------------------------

    async def task_start(self, goal: str, session_id: str = "",
                         task_id: Optional[str] = None,
                         cwd: Optional[str] = None,
                         provider: str = "", model: str = "") -> str:
        task_id = task_id or uuid.uuid4().hex[:12]
        now = time.time()
        await self._aexec(
            "INSERT OR REPLACE INTO tasks (task_id, goal, status, session_id, created_at,"
            " updated_at, cwd, provider, model) VALUES (?,?,?,?,?,?,?,?,?)",
            (task_id, goal[:2000], "in_progress", session_id, now, now,
             cwd or os.getcwd(), provider, model),
        )
        await self._log(task_id, "task_start", None, {"goal": goal[:500]})
        from app.activity import emit
        emit("task_start", task_id=task_id, goal=goal[:80])
        return task_id

    async def task_update(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols, vals = [], []
        for k, v in fields.items():
            if k in ("progress", "files_changed", "commands", "plan",
                     "decisions", "test_results", "recovery_actions"):
                v = json.dumps(v, ensure_ascii=False)
            elif k == "verification":
                v = json.dumps(v, ensure_ascii=False)
            cols.append(f"{k}=?")
            vals.append(v)
        cols.append("updated_at=?")
        vals.append(time.time())
        vals.append(task_id)
        await self._aexec(f"UPDATE tasks SET {', '.join(cols)} WHERE task_id=?", tuple(vals))

    async def task_complete(self, task_id: str) -> None:
        await self.task_update(task_id, status="completed")
        await self._log(task_id, "task_complete", None, {})
        from app.activity import emit
        emit("task_complete", task_id=task_id)

    async def task_fail(self, task_id: str, error: str) -> None:
        await self.task_update(task_id, status="failed", last_error=error[:1000])
        await self._log(task_id, "task_error", None, {"error": error[:500]})
        from app.activity import emit
        emit("task_error", task_id=task_id, error=error[:80])

    async def task_pause(self, task_id: str) -> None:
        await self.task_update(task_id, status="paused")

    async def mark_interrupted_running_tasks(self) -> int:
        """On startup: any 'in_progress' task from a dead process becomes
        'interrupted' so /resume can find it (spec §9)."""
        rows = await self._aquery(
            "SELECT task_id FROM tasks WHERE status IN ('in_progress','paused')"
        )
        for r in rows:
            await self.task_update(r["task_id"], status="interrupted")
        return len(rows)

    # ------------------------------------------------------------------
    # Progress / action records (spec §8, §33, §36)
    # ------------------------------------------------------------------

    async def _log(self, task_id: str, kind: str, tool: Optional[str],
                   detail: dict) -> None:
        await self._aexec(
            "INSERT INTO journal (task_id, ts, kind, tool, detail) VALUES (?,?,?,?,?)",
            (task_id, time.time(), kind, tool,
             json.dumps(detail, ensure_ascii=False)[:4000]),
        )

    async def record_action(self, task_id: str, tool: str, args: dict,
                            success: bool, output: Optional[str] = None,
                            error: Optional[str] = None, attempt: int = 1) -> None:
        """Called after EVERY tool execution (spec §8 checkpoint list)."""
        desc = self._describe(tool, args)
        fields: Dict[str, Any] = {}
        if success:
            fields["last_success"] = f"{tool}: {desc}"[:500]
        else:
            fields["last_error"] = f"{tool}: {error or 'unknown error'}"[:500]
        await self.task_update(task_id, **fields)
        await self._log(task_id, "tool_success" if success else "tool_failure", tool, {
            "args_preview": str(args)[:500],
            "output_preview": (output or "")[:500],
            "error": (error or "")[:500],
            "attempt": attempt,
        })

    async def record_step(self, task_id: str, step_count: int,
                          tool_calls: int, current_step: str = "") -> None:
        await self.task_update(
            task_id, step_count=step_count, tool_calls=tool_calls,
            current_step=(current_step or f"step {step_count}")[:300],
        )

    async def record_progress(self, task_id: str, completed: List[str],
                              in_progress: List[str], pending: List[str]) -> None:
        await self.task_update(task_id, progress={
            "completed": [str(x)[:200] for x in completed],
            "in_progress": [str(x)[:200] for x in in_progress],
            "pending": [str(x)[:200] for x in pending],
        })

    async def record_file_change(self, task_id: str, path: str,
                                 op: str = "modified") -> None:
        row = (await self._aquery(
            "SELECT files_changed FROM tasks WHERE task_id=?", (task_id,)))
        files: List[dict] = json.loads(row[0]["files_changed"]) if row else []
        # Dedup on path, keep latest op.
        files = [f for f in files if f.get("path") != path]
        files.append({"path": path, "op": op, "ts": time.time()})
        if len(files) > 400:
            files = files[-400:]
        await self.task_update(task_id, files_changed=files)
        await self._log(task_id, "file_change", None, {"path": path, "op": op})

    async def record_command(self, task_id: str, command: str,
                             status: str = "ran") -> None:
        row = (await self._aquery(
            "SELECT commands FROM tasks WHERE task_id=?", (task_id,)))
        cmds: List[dict] = json.loads(row[0]["commands"]) if row else []
        cmds.append({"cmd": command[:500], "status": status, "ts": time.time()})
        if len(cmds) > 400:
            cmds = cmds[-400:]
        await self.task_update(task_id, commands=cmds)
        await self._log(task_id, "command", None, {"cmd": command[:500]})

    @staticmethod
    def _describe(tool: str, args: dict) -> str:
        for key in ("path", "file_path", "command", "cmd", "query", "url", "code"):
            if key in args:
                v = str(args[key])
                return v[:120]
        return str(args)[:120]

    # ------------------------------------------------------------------
    # Work State 2.0 (spec §9): decisions, tests, recovery, blocked, phase
    # ------------------------------------------------------------------

    async def _append_json_col(self, task_id: str, col: str, item: dict) -> None:
        row = (await self._aquery(
            f"SELECT {col} FROM tasks WHERE task_id=?", (task_id,)))
        cur: list = json.loads(row[0][col]) if row and row[0][col] else []
        cur.append(item)
        if len(cur) > 200:
            cur = cur[-200:]
        await self._aexec(
            f"UPDATE tasks SET {col}=?, updated_at=? WHERE task_id=?",
            (json.dumps(cur, ensure_ascii=False), time.time(), task_id))

    async def record_decision(self, task_id: str, decision: str,
                              rationale: str = "") -> None:
        await self._append_json_col(task_id, "decisions", {
            "decision": decision[:500], "rationale": rationale[:300],
            "ts": time.time()})
        await self._log(task_id, "decision", None,
                        {"decision": decision[:300]})

    async def record_test_result(self, task_id: str, name: str, passed: bool,
                                 detail: str = "") -> None:
        await self._append_json_col(task_id, "test_results", {
            "name": name[:200], "passed": bool(passed),
            "detail": detail[:400], "ts": time.time()})

    async def record_recovery(self, task_id: str, action: str,
                              outcome: str = "") -> None:
        await self._append_json_col(task_id, "recovery_actions", {
            "action": action[:400], "outcome": outcome[:300],
            "ts": time.time()})

    async def set_phase(self, task_id: str, phase: str) -> None:
        await self.task_update(task_id, phase=phase[:120])

    async def set_blocked(self, task_id: str, reason: str,
                          needed: str = "", completed: str = "",
                          next_action: str = "") -> None:
        """Human-dependency detection (spec §47): record WHY the task is
        blocked, what finished, what is needed, and the next action —
        the task is never lost."""
        await self.task_update(task_id, status="blocked",
                               blocked_reason=reason[:1000],
                               next_action=next_action[:500])
        await self._log(task_id, "blocked", None, {
            "reason": reason[:300], "needed": needed[:300],
            "completed": completed[:300]})

    async def record_verification(self, task_id: str, result: dict) -> None:
        result = dict(result)
        result["ts"] = time.time()
        await self.task_update(task_id, verification=result)
        await self._log(task_id, "verification", None, {
            "k": result.get("kind"), "ok": result.get("ok"),
            "summary": str(result.get("summary", ""))[:300]})

    # ------------------------------------------------------------------
    # Checkpoints — atomic memory snapshots (spec §8, §43)
    # ------------------------------------------------------------------

    def _checkpoint_path(self, task_id: str) -> Path:
        safe = "".join(c for c in task_id if c.isalnum() or c in "-_")
        return self.checkpoint_dir / f"{safe}.json"

    def _write_atomic(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)  # atomic — crash cannot corrupt previous state
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    async def checkpoint(self, task_id: str, step_count: int,
                         memory_messages: List[dict], goal: str = "",
                         provider: str = "", model: str = "") -> None:
        """Persist a full, restorable snapshot after every meaningful op."""
        data = {
            "task_id": task_id,
            "goal": goal[:2000],
            "step_count": step_count,
            "saved_at": time.time(),
            "provider": provider,
            "model": model,
            "cwd": os.getcwd(),
            "memory": memory_messages,
        }
        try:
            await asyncio.to_thread(self._write_atomic,
                                    self._checkpoint_path(task_id), data)
            await self._log(task_id, "checkpoint", None,
                            {"step": step_count, "messages": len(memory_messages)})
            from app.activity import emit
            emit("checkpoint", task_id=task_id, step=step_count,
                 saved_at=data["saved_at"])
        except Exception as e:
            logger.error(f"[Journal] checkpoint write failed: {e}")

    def load_checkpoint_sync(self, task_id: str) -> Optional[dict]:
        p = self._checkpoint_path(task_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[Journal] checkpoint read failed for {task_id}: {e}")
            return None

    async def load_checkpoint(self, task_id: str) -> Optional[dict]:
        try:
            return await asyncio.to_thread(self.load_checkpoint_sync, task_id)
        except Exception as e:
            logger.error(f"[Journal] checkpoint read failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Queries for /status /tasks /resume /history (spec §11, §12)
    # ------------------------------------------------------------------

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        rows = await self._aquery("SELECT * FROM tasks WHERE task_id=?", (task_id,))
        if not rows:
            return None
        t = rows[0]
        for col, default in (("progress", "{}"), ("files_changed", "[]"),
                             ("commands", "[]"), ("plan", "[]"),
                             ("decisions", "[]"), ("test_results", "[]"),
                             ("recovery_actions", "[]"), ("verification", "{}")):
            raw = t.get(col)
            if isinstance(raw, str) or raw is None:
                try:
                    t[col] = json.loads(raw or default)
                except (TypeError, json.JSONDecodeError):
                    t[col] = json.loads(default)
        return t

    async def list_tasks(self, status: Optional[str] = None,
                         limit: int = 30) -> List[Dict[str, Any]]:
        if status:
            rows = await self._aquery(
                "SELECT * FROM tasks WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                (status, limit))
        else:
            rows = await self._aquery(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,))
        for t in rows:
            t["progress"] = json.loads(t.get("progress") or "{}")
        return rows

    async def last_interrupted(self) -> Optional[Dict[str, Any]]:
        # v3.0.3: workspace-scoped — only surface interrupted tasks that were
        # started in THIS directory. A global journal previously leaked stale
        # tasks from other projects into every fresh REPL/banner ("Previous
        # task detected: <unrelated old goal>"). NULL-cwd legacy rows are
        # still considered so pre-upgrade state remains resumable.
        rows = await self._aquery(
            "SELECT * FROM tasks WHERE status='interrupted'"
            " AND (cwd IS NULL OR cwd=?) ORDER BY updated_at DESC LIMIT 1",
            (os.getcwd(),))
        if not rows:
            return None
        t = rows[0]
        t["progress"] = json.loads(t.get("progress") or "{}")
        return t

    async def events(self, task_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self._aquery(
            "SELECT * FROM journal WHERE task_id=? ORDER BY ts DESC LIMIT ?",
            (task_id, limit))

    async def current_status(self) -> Dict[str, Any]:
        """Composite status for /status (spec §11)."""
        active = await self._aquery(
            "SELECT * FROM tasks WHERE status IN ('in_progress','paused','interrupted')"
            " ORDER BY updated_at DESC LIMIT 1")
        stats = await self._aquery(
            "SELECT status, COUNT(*) as n FROM tasks GROUP BY status")
        by_status = {r["status"]: r["n"] for r in stats}
        latest_events = await self._aquery(
            "SELECT * FROM journal ORDER BY ts DESC LIMIT 5")
        t = active[0] if active else None
        if t:
            # deserialize ALL JSON columns (Work State 2.0 included)
            t = await self.get_task(t["task_id"]) or t
        last_cp = None
        if t:
            cp = self.load_checkpoint_sync(t["task_id"])
            if cp:
                last_cp = cp.get("saved_at")
        return {
            "active_task": t,
            "tasks_by_status": by_status,
            "recent_events": list(reversed(latest_events)),
            "last_checkpoint_ts": last_cp,
        }

    def progress_percent(self, task: Dict[str, Any]) -> int:
        prog = task.get("progress") or {}
        items = (prog.get("completed") or []) + (prog.get("in_progress") or []) + (prog.get("pending") or [])
        if not items:
            # Fall back to step-based estimate vs. nothing — never fake 100%.
            return 0
        done = len(prog.get("completed") or [])
        return int(100.0 * done / len(items))


# ──────────────────────────────────────────────────────────────────────────────
# Provider-independent STATE kv layer (spec §5: PROJECT_STATE, PROVIDER_STATE,
# MODEL_STATE, MEMORY_STATE, RECOVERY_STATE ... persisted independently of LLM)
# ──────────────────────────────────────────────────────────────────────────────

class StateStore:
    """Key/value persistent state, JSON files with atomic writes.

    Keys (spec §5): project, task, conversation, memory, file, tool, command,
    error, provider, model, checkpoint, recovery — anything the caller wants.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else STATE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    _SPECIAL = {"project", "task", "conversation", "memory", "file", "tool",
                "command", "error", "provider", "model", "checkpoint", "recovery"}

    def _path(self, key: str) -> Path:
        key = key.lower().strip()
        if key not in self._SPECIAL and not key.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"invalid state key: {key!r}")
        return self.root / f"state_{key}.json"

    def get(self, key: str, default: Any = None) -> Any:
        try:
            p = self._path(key)
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[StateStore] read {key} failed: {e}")
        return default

    def set(self, key: str, value: Any) -> bool:
        try:
            p = self._path(key)  # raises ValueError on invalid keys (programmer error)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, p)
            return True
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"[StateStore] write {key} failed: {e}")
            return False

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except Exception:
            pass

    def keys(self) -> List[str]:
        return sorted(p.stem.replace("state_", "") for p in self.root.glob("state_*.json"))


_state_store: Optional[StateStore] = None


def get_state_store() -> StateStore:
    global _state_store
    if _state_store is None:
        _state_store = StateStore()
    return _state_store
