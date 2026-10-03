from __future__ import annotations

"""
SHS Code HTTP/WebSocket Server
================================
FastAPI backend that exposes the full SHS Code agent engine via:
  • REST API   — session management, history queries, tool introspection
  • WebSocket  — real-time streaming of agent thoughts, tool calls, and outputs
  • API Key    — optional authentication via SHSCODE_API_KEY env var
  • CORS       — configurable via SHSCODE_ALLOWED_ORIGINS env var

Run with:
  python run_server.py
  # or
  uvicorn app.server.main:app --host 0.0.0.0 --port 8765 --reload
"""

import asyncio
import json
import os
import time
from collections import OrderedDict
from typing import Any, Optional

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db.session import SessionDB
from app.logger import logger
from app.permissions.gate import AgentMode
from app import env

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Startup/shutdown lifecycle.

    SHS Code FIX (registry regression): on startup, sessions left 'running'
    by a previous crashed server are recovered to 'interrupted' so the
    registry can never show phantom running sessions; on shutdown, tasks
    still running are cancelled and their sessions closed with the real
    final state instead of staying 'running' forever.
    """
    if not _API_KEY:
        logger.warning(
            "SHSCODE_API_KEY not set — all endpoints are UNAUTHENTICATED. "
            "Set SHSCODE_API_KEY in production."
        )
    # v4.3.0 (mandatory attribution): every git commit made by this server —
    # GUI GitHub panel, terminal panel, agent bash sessions — is attributed
    # to the SHS-Code-Agent profile (author + committer + trailer), enforced
    # by the git shim on PATH + forced env. There is deliberately NO opt-out.
    try:
        from app.git_providers.agent_identity import apply_agent_git_env
        if apply_agent_git_env():
            from app.git_providers.git_shim import shim_active_on_path
            logger.info(
                "[Server] Git identity enforced: SHS-Code-Agent "
                f"(git shim active: {shim_active_on_path()}) — mandatory, "
                "no opt-out")
    except Exception as e:
        logger.warning(f"[Server] Agent git-identity setup failed: {e}")
    logger.info("SHS Code Agent Server started.")
    application.state.background_tasks = set()
    application.state.session_tasks = {}   # session_id -> asyncio.Task
    try:
        recovered = await db.recover_stale_sessions(before_ts=_BOOT_TIME)
        if recovered:
            logger.info(
                f"[Server] Recovered {recovered} stale 'running' session(s) "
                "from a previous process -> 'interrupted'."
            )
    except Exception as e:
        logger.warning(f"[Server] Stale-session recovery failed: {e}")
    yield
    # Cleanup: cancel any still-running background agent tasks AND close
    # their sessions so the registry reflects reality after shutdown.
    bg = getattr(application.state, "background_tasks", set())
    session_tasks = getattr(application.state, "session_tasks", {})
    if bg:
        logger.info(f"[Server] Cancelling {len(bg)} background task(s) on shutdown.")
        for t in list(bg):
            t.cancel()
        import asyncio as _asyncio
        await _asyncio.gather(*bg, return_exceptions=True)
    # Mark sessions whose tasks were cancelled while still 'running'.
    try:
        for sid in list(session_tasks.keys()):
            row = await db.get_session(sid)
            if row and row.get("state") == "running":
                await db.close_session(sid, state="interrupted",
                                       step_count=row.get("step_count") or 0)
    except Exception as e:
        logger.warning(f"[Server] Shutdown session close failed: {e}")
    logger.info("SHS Code Agent Server shut down cleanly.")


_BOOT_TIME = time.time()

app = FastAPI(
    title="SHS Code Agent Server",
    description="Persistent autonomous coding agent engine by SHS Lab (Sazzad Hussain Shobuj)",
    version=__import__("app").__version__,
    lifespan=_lifespan,
)

_raw_origins = env.getenv("ALLOWED_ORIGINS", "")
_allowed_origins: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else []
)

if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Fix: In production, CORS must not allow all origins by default.
    # Instead, require explicit configuration. We still allow it in dev mode
    # for developer convenience but log a clear warning.
    logger.warning(
        "SHSCODE_ALLOWED_ORIGINS not set — CORS allows all origins. "
        "Set SHSCODE_ALLOWED_ORIGINS in production to restrict access."
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

_API_KEY = env.getenv("API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Static files directory
_STATIC_DIR = Path(__file__).parent / "static"

# API key authentication


async def require_api_key(key: Optional[str] = Depends(_api_key_header)) -> None:
    if not _API_KEY:
        return
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


class ConnectionManager:
    """v4.0.1 (mission §14/§15): multi-socket session registry.

    The old manager kept ONE socket per session — a second tab/viewer
    silently replaced the first, and the chat endpoint's sockets lived in
    a DIFFERENT registry so they never received agent events at all.
    Now every consumer (GUI, chat, /ws) registers here and every frame
    fans out to ALL sockets watching that session.
    """

    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, session_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self.active.setdefault(session_id, []).append(ws)

    def disconnect_one(self, ws: WebSocket, session_id: str) -> None:
        conns = self.active.get(session_id)
        if conns and ws in conns:
            conns.remove(ws)
            if not conns:
                self.active.pop(session_id, None)

    def disconnect(self, session_id: str) -> None:
        self.active.pop(session_id, None)

    async def send(self, session_id: str, data: dict) -> None:
        """Fan a frame out to every socket watching this session."""
        payload = json.dumps(data)
        for ws in list(self.active.get(session_id, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect_one(ws, session_id)

    async def broadcast(self, data: dict) -> None:
        payload = json.dumps(data)
        for sid in list(self.active.keys()):
            for ws in list(self.active.get(sid, [])):
                try:
                    await ws.send_text(payload)
                except Exception:
                    self.disconnect_one(ws, sid)


manager = ConnectionManager()
db = SessionDB()

# ─── Canvas & Chat integration ──────────────────────────────────────────

# Canvas chat connection manager (multiple clients per session)
# FIX: Use OrderedDict with max size to prevent unbounded memory growth.
# When sessions exceed the limit, the oldest is evicted.
_MAX_CANVAS_SESSIONS = 256
canvas_chat_manager: OrderedDict = OrderedDict()

# Lazy-init canvas server
def _get_canvas_server():
    from app.canvas.server import CanvasServer
    srv = getattr(app.state, "canvas_server", None)
    if srv is None:
        srv = CanvasServer()
        app.state.canvas_server = srv
    return srv



class StreamingSHSCode:
    """Wraps SHSCode agent with WebSocket event emission and unified session tracking.

    SHS Code FIX (registry regression): records the agent's REAL final state
    (state / step_count / error) so callers can close the session with
    accurate values; the agent itself is the primary writer (BaseAgent.run
    now always closes sessions, including injected ones).

    v4.0.1 (mission §15 — GUI must not scrape terminal output): while the
    agent runs, the ActivityBus is bridged to the session's WebSocket
    sockets as STRUCTURED event frames — llm_delta (token streaming),
    tool_start/tool_end, plan_created, checkpoint, task lifecycle. The
    frames use an `event` field (type is mirrored for legacy clients).
    """

    # ActivityBus kinds forwarded to sockets (internal → UI-safe set)
    _FORWARDED = {
        "llm_delta", "llm_start", "llm_end",
        "tool_start", "tool_end", "tool_error",
        "step", "plan_created", "checkpoint", "verifying",
        "parallel_tools", "review_phase", "rollback_snapshot",
        "subagent_start", "subagent_end", "blocked", "context_compacted",
        "memory_recall", "rate_limit_wait", "rate_limit_resume",
        "model_switch", "provider_switch", "llm_fallback",
        "task_start", "task_complete", "task_error", "task_partial",
    }

    # v4.0.1: bridges of currently-running streams — lets a bridge decide
    # whether an UNATTRIBUTED event (no session_id) belongs to it. With
    # multiple concurrent runs, unattributed events are dropped rather than
    # cross-delivered to the wrong session's UI.
    _active_bridges: dict[str, object] = {}

    def __init__(self, session_id: str, mode: AgentMode = AgentMode.BUILD, max_steps: Optional[int] = None) -> None:
        self.session_id = session_id
        self.mode = mode
        self.max_steps = max_steps
        self.last_state: str = ""
        self.last_step_count: int = 0
        self.last_error: Optional[str] = None

    def _activity_bridge(self, kind: str, data: dict) -> None:
        if kind not in self._FORWARDED:
            return
        # session-attributed events must match THIS stream's session
        ev_sid = data.get("session_id") if isinstance(data, dict) else None
        if ev_sid and ev_sid != self.session_id:
            return
        # unattributed events (LLM-layer level) are only safe to forward
        # when a single run is active — otherwise they could belong to any
        # concurrent run and would cross-pollute the wrong UI
        if not ev_sid and len(self._active_bridges) > 1:
            return
        frame = {"event": kind, "type": kind, "session_id": self.session_id,
                 "ts": time.time()}
        frame.update(data if isinstance(data, dict) else {})
        # fire-and-forget: bridge onto the running loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.send(self.session_id, frame))
        except RuntimeError:
            pass

    async def run(self, prompt: str) -> str:
        from app.agent.shscode import SHSCode

        agent = SHSCode(mode=self.mode, session_id=self.session_id)
        if self.max_steps is not None:
            agent._max_steps = self.max_steps

        original_step = agent.step

        async def patched_step():
            # v4.0.1 fix: BaseAgent.run increments _step_count BEFORE calling
            # step() — the old `+1` double-counted (step_start said 2 on the
            # first step). Report the CURRENT step number.
            step_num = agent._step_count
            await manager.send(self.session_id, {
                "event": "step_start", "type": "step_start",
                "step": step_num, "ts": time.time(),
            })
            result = await original_step()
            if result:
                await manager.send(self.session_id, {
                    "event": "step_output", "type": "step_output",
                    "step": step_num,
                    "content": result[:2000], "ts": time.time(),
                })
            return result

        agent.step = patched_step  # type: ignore

        # v4.0.1: bridge runtime activity to the session sockets
        from app.activity import ActivityBus
        ActivityBus.subscribe(self._activity_bridge)
        self._active_bridges[self.session_id] = self
        try:
            await manager.send(self.session_id, {
                "event": "agent_start", "type": "agent_start",
                "prompt": prompt[:200], "ts": time.time()})
            final = await agent.run(prompt)
            self.last_state = getattr(agent.state, "value", str(agent.state))
            self.last_step_count = agent._step_count
            await manager.send(self.session_id, {
                "event": "agent_done", "type": "agent_done",
                "output": final[:4000],
                "state": agent.state.value,
                "finish_reason": getattr(agent, "_finish_reason", ""),
                "steps": agent._step_count,
                "ts": time.time(),
            })
            return final
        except asyncio.CancelledError:
            # Server shutdown / client cancellation — the agent's finally
            # block has already closed the session as 'interrupted'.
            self.last_state = "interrupted"
            self.last_step_count = agent._step_count
            raise
        except Exception as e:
            self.last_state = "error"
            self.last_step_count = agent._step_count
            self.last_error = str(e)
            await manager.send(self.session_id, {
                "event": "agent_error", "type": "agent_error",
                "error": str(e), "ts": time.time(),
            })
            raise
        finally:
            ActivityBus.unsubscribe(self._activity_bridge)
            self._active_bridges.pop(self.session_id, None)


class RunRequest(BaseModel):
    prompt: str
    mode: str = "build"
    # v4.3.0: max_steps is USER-CONTROLLED. None (the default) means "use
    # the configured value" (env override > config files > default 30) —
    # the old hardcoded ``= 30`` here silently stomped any configured value
    # on every GUI/API run, which is exactly the bug the user hit: they
    # configured 80, the runtime used 30.
    max_steps: Optional[int] = None
    session_id: Optional[str] = None   # v4.0.1: continue an existing session
    # v4.3.0: run the task as a DETACHED OS process instead of an in-server
    # asyncio task — survives server restarts and shell/session death.
    detach: bool = False


class RunResponse(BaseModel):
    session_id: str
    status: str
    output: Optional[str] = None
    run_id: Optional[str] = None      # v4.3.0: detached run registry id
    log_path: Optional[str] = None    # v4.3.0: detached run log


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": __import__("app").__version__, "agent": "SHS Code"}


@app.get("/")
async def root():
    return {"message": "SHS Code Agent Server — connect via /ws/<session_id>"}


@app.post("/run", response_model=RunResponse, dependencies=[Depends(require_api_key)])
async def run_agent(req: RunRequest):
    mode = AgentMode.PLAN if req.mode.lower() == "plan" else AgentMode.BUILD
    mode_str = mode.value
    # v4.3.0: an explicitly supplied max_steps must be a positive integer —
    # reject with 400 instead of silently coercing/falling back.
    if req.max_steps is not None and (not isinstance(req.max_steps, int) or req.max_steps < 1):
        raise HTTPException(status_code=400,
                            detail="max_steps must be an integer >= 1")
    # v4.0.1 (mission §16 — CLI/GUI shared state): an explicit session_id
    # CONTINUES that session (conversation history is re-injected by the
    # agent). Previously POST /run always created a new session — the GUI
    # could not continue a conversation over REST.
    if req.session_id:
        row = await db.get_session(req.session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        session_id = req.session_id
    else:
        session_id = await db.create_session(req.prompt, mode=mode_str)  # Fix: use enum value

    # v4.3.0 (lifecycle): a DETACHED run is a double-forked OS process — it
    # survives this server's restart/death, keeps checkpointing to the
    # sessions DB, and is resumable. In-server asyncio tasks (below) die
    # with the process; long autonomous work belongs on the detached path.
    if req.detach:
        from app.daemon import start_detached_run, new_run_id
        import sys as _sys
        run_id = new_run_id()
        daemon_argv = ["-m", "app", req.prompt, "--session", session_id]
        if req.max_steps is not None:
            daemon_argv += ["--max-steps", str(req.max_steps)]
        os.environ["SHSCODE_DETACHED_RUN_ID"] = run_id
        info = start_detached_run(
            daemon_argv, run_id=run_id, session_id=session_id,
            prompt=req.prompt, detached_by="server", cwd=os.getcwd())
        return RunResponse(session_id=session_id, status="detached",
                           run_id=run_id, log_path=info.get("log_path"))

    async def _run():
        streamer = StreamingSHSCode(session_id=session_id, mode=mode, max_steps=req.max_steps)
        try:
            await streamer.run(req.prompt)
        except asyncio.CancelledError:
            # Shutdown: BaseAgent.run's finally already closed the session as
            # 'interrupted'. Nothing more to do.
            raise
        except Exception as e:
            logger.error(f"[Server] Agent run error: {e}")
            # Defense in depth: the agent closes its session in its own
            # finally, but if anything slipped through, close it now with
            # the real error so the registry never stays 'running'.
            try:
                row = await db.get_session(session_id)
                if row and row.get("state") == "running":
                    await db.close_session(
                        session_id, state="error",
                        step_count=streamer.last_step_count,
                        error=str(e)[:2048])
            except Exception:
                pass

    # Fix: store task reference to prevent GC and lost errors
    task = asyncio.create_task(_run())
    _bg = getattr(app.state, 'background_tasks', set())
    _bg.add(task)
    task.add_done_callback(_bg.discard)
    app.state.background_tasks = _bg
    _st = getattr(app.state, 'session_tasks', {})
    _st[session_id] = task
    task.add_done_callback(lambda _t, _sid=session_id: _st.pop(_sid, None))
    app.state.session_tasks = _st
    return RunResponse(session_id=session_id, status="running")


@app.post("/run/sync", response_model=RunResponse, dependencies=[Depends(require_api_key)])
async def run_agent_sync(req: RunRequest):
    from app.agent.shscode import SHSCode
    mode = AgentMode.PLAN if req.mode.lower() == "plan" else AgentMode.BUILD
    mode_str = mode.value
    session_id = await db.create_session(req.prompt, mode=mode_str)  # Fix: use enum value
    try:
        agent = SHSCode(mode=mode, session_id=session_id)
        agent._max_steps = req.max_steps
        output = await agent.run(req.prompt)
        # SHS Code FIX (registry regression): BaseAgent.run closes the session
        # itself (including injected ids) with the real state + step count.
        # This close is a verification layer — it only fires if the agent's
        # own close somehow missed, and uses REAL values (never 0).
        row = await db.get_session(session_id)
        if row and row.get("state") == "running":
            await db.close_session(
                session_id, state="finished", step_count=agent._step_count)
        return RunResponse(session_id=session_id, status="finished", output=output)
    except Exception as e:
        # SHS Code FIX: preserve the REAL step count on the error path (the
        # agent's own finally already closed the session; only repair if it
        # somehow stayed open — never clobber progress back to 0).
        row = await db.get_session(session_id)
        if row and row.get("state") == "running":
            await db.close_session(session_id, state="error",
                                   step_count=row.get("step_count") or 0,
                                   error=str(e)[:2048])
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions", dependencies=[Depends(require_api_key)])
async def list_sessions(limit: int = 20):
    sessions = await db.get_sessions(limit=limit)
    return {"sessions": sessions}


@app.get("/runs", dependencies=[Depends(require_api_key)])
async def list_detached_runs(limit: int = 25):
    """v4.3.0: detached-run registry + live process liveness (GUI)."""
    from app.daemon import list_runs
    return {"runs": list_runs(limit=limit)}


@app.get("/runs/{run_id}", dependencies=[Depends(require_api_key)])
async def detached_run_detail(run_id: str):
    """v4.3.0: one detached run — registry entry + current session state."""
    from app.daemon import get_run
    info = get_run(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail="run not found")
    sid = info.get("session_id")
    if sid:
        row = await db.get_session(sid)
        if row:
            info["session_state"] = row.get("state")
            info["session_steps"] = row.get("step_count")
    return info


@app.get("/sessions/{session_id}", dependencies=[Depends(require_api_key)])
async def get_session_detail(session_id: str):
    """v4.0.1 (mission §14): single-session detail for the GUI — registry
    row + running-task status + socket viewer count."""
    row = await db.get_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    _st = getattr(app.state, "session_tasks", {})
    task = _st.get(session_id)
    return {
        "session": row,
        "running": bool(task and not task.done()),
        "viewers": len(manager.active.get(session_id, [])),
    }


@app.post("/sessions/{session_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel_session(session_id: str):
    """v4.0.1 (mission §14 — GUI cancellation): cancel a running session.
    The agent's checkpointing already persists state — the run resumes
    from where it stopped."""
    _st = getattr(app.state, "session_tasks", {})
    task = _st.get(session_id)
    if task and not task.done():
        task.cancel()
        return {"cancelled": True, "session_id": session_id}
    return {"cancelled": False, "detail": "no running task for this session"}


@app.get("/tasks", dependencies=[Depends(require_api_key)])
async def list_journal_tasks(limit: int = 30):
    """v4.0.1 (mission §14 — GUI Tasks panel): journal task rows (the
    persisted task lifecycle: in_progress / completed / partial / failed /
    blocked / interrupted)."""
    from app.state import Journal
    try:
        j = Journal.get()
        rows = await j._aquery(
            "SELECT task_id, goal, status, step_count, tool_calls, cwd, "
            "provider, model, created_at, updated_at, blocked_reason "
            "FROM tasks ORDER BY updated_at DESC LIMIT ?", (int(limit),))
        return {"tasks": rows}
    except Exception as e:
        return {"tasks": [], "error": str(e)}


@app.get("/tasks/{task_id}", dependencies=[Depends(require_api_key)])
async def get_journal_task(task_id: str):
    """v4.0.1: task detail + DAG nodes + journal tail for the GUI."""
    from app.state import Journal
    try:
        j = Journal.get()
        task = await j.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        nodes = await j._aquery(
            "SELECT node_id, title, status, priority, depends_on, files, "
            "notes, attempts FROM task_nodes WHERE task_id=?", (task_id,))
        events = await j._aquery(
            "SELECT ts, kind, tool, detail FROM journal WHERE task_id=? "
            "ORDER BY id DESC LIMIT 50", (task_id,))
        return {"task": task, "nodes": nodes, "events": events}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workspace/files", dependencies=[Depends(require_api_key)])
async def workspace_files(path: str = "."):
    """v4.0.1 (mission §14 — GUI Workspace panel): safe file tree listing.
    Paths are confined to the server's working directory; hidden dirs,
    __pycache__, node_modules and .git are skipped."""
    import os as _os
    root = _os.path.abspath(_os.getcwd())
    target = _os.path.abspath(_os.path.join(root, path))
    if not target.startswith(root):
        raise HTTPException(status_code=400, detail="path escapes workspace")
    if not _os.path.isdir(target):
        raise HTTPException(status_code=404, detail="not a directory")
    _SKIP = {"__pycache__", "node_modules", ".git", ".venv", "venv",
             ".mypy_cache", ".pytest_cache", ".shscode"}
    entries = []
    try:
        for name in sorted(_os.listdir(target))[:500]:
            if name.startswith(".") and name not in (".env.example",):
                continue
            full = _os.path.join(target, name)
            rel = _os.path.relpath(full, root)
            try:
                is_dir = _os.path.isdir(full)
                size = 0 if is_dir else _os.path.getsize(full)
            except OSError:
                continue
            if is_dir and name in _SKIP:
                continue
            entries.append({"name": name, "path": rel, "dir": is_dir,
                            "size": size})
        return {"root": root, "path": path, "entries": entries}
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workspace/file", dependencies=[Depends(require_api_key)])
async def workspace_file(path: str, max_bytes: int = 200000):
    """v4.0.1: read a workspace file (confined to cwd, size-capped)."""
    import os as _os
    root = _os.path.abspath(_os.getcwd())
    target = _os.path.abspath(_os.path.join(root, path))
    if not target.startswith(root):
        raise HTTPException(status_code=400, detail="path escapes workspace")
    if not _os.path.isfile(target):
        raise HTTPException(status_code=404, detail="not a file")
    try:
        size = _os.path.getsize(target)
        with open(target, "r", errors="replace") as f:
            content = f.read(max_bytes)
        return {"path": path, "size": size, "truncated": size > max_bytes,
                "content": content}
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/git/status", dependencies=[Depends(require_api_key)])
async def git_status():
    """v4.0.1 (mission §14 — GUI Git panel): branch, changed files,
    recent commits. Graceful when cwd is not a repository."""
    import subprocess

    def _run(cmd):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=10, cwd=".")
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch is None:
        return {"is_repo": False}
    return {
        "is_repo": True,
        "branch": branch,
        "status": _run(["git", "status", "--porcelain"]),
        "log": _run(["git", "log", "--oneline", "-10"]),
    }


# ─── Workspace diff-viewer (v4.2.0 — mission follow-up) ────────────────────

_WS_DIFF_MODES = {
    "unstaged": ["diff", "--no-color", "--unified=3"],
    "staged":   ["diff", "--cached", "--no-color", "--unified=3"],
    "head":     ["diff", "HEAD", "--no-color", "--unified=3"],
}


def _parse_unified_diff(raw: str) -> dict:
    """Split a unified diff into per-file sections.

    Returns {path_after: {"diff": str, "additions": int, "deletions": int,
    "binary": bool}}. Paths come from the ``+++ b/<path>`` header lines,
    which is also correct for renames and new/deleted files."""
    files: dict = {}
    current_path = None
    current_lines: list = []
    additions = deletions = 0
    binary = False

    def _flush():
        nonlocal current_path, current_lines, additions, deletions, binary
        if current_path is not None:
            files[current_path] = {
                "diff": "\n".join(current_lines),
                "additions": additions,
                "deletions": deletions,
                "binary": binary,
            }
        current_path, current_lines = None, []
        additions = deletions = 0
        binary = False

    for line in raw.splitlines():
        if line.startswith("diff --git "):
            _flush()
            current_lines = [line]
        elif line.startswith("+++ b/"):
            # rename/copy targets show "+++ b/<new>"; plain files too
            current_path = line[6:].strip() or current_path
            current_lines.append(line)
        elif line.startswith("+++ /dev/null"):
            # deleted file: the path only appears in the "--- a/" header
            current_lines.append(line)
        elif line.startswith("--- a/"):
            if current_path is None:
                current_path = line[6:].strip()
            current_lines.append(line)
        elif current_path is not None or current_lines:
            if line.startswith("Binary files") or line.startswith("GIT binary patch"):
                binary = True
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
            current_lines.append(line)
    _flush()
    return files


@app.get("/workspace/diff", dependencies=[Depends(require_api_key)])
async def workspace_diff(mode: str = "unstaged", max_bytes: int = 200000):
    """v4.2.0 (GUI workspace diff-viewer): structured diff of working-tree
    changes. ``mode`` is ``unstaged`` (default), ``staged``, or ``head``
    (staged + unstaged vs HEAD). Untracked files are included as synthetic
    new-file diffs. Graceful when cwd is not a repository."""
    import subprocess

    if mode not in _WS_DIFF_MODES:
        raise HTTPException(status_code=400,
                            detail="mode must be unstaged|staged|head")

    def _run(cmd) -> str | None:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=15, cwd=".")
            return out.stdout if out.returncode == 0 else None
        except Exception:
            return None

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch is None:
        return {"is_repo": False, "branch": "", "files": [],
                "summary": {"files": 0, "additions": 0, "deletions": 0},
                "mode": mode, "truncated": False}
    branch = branch.strip()

    # statuses via porcelain (XY codes) — untracked = "??"
    statuses: dict = {}
    porcelain = _run(["git", "status", "--porcelain"])
    if porcelain is not None:
        for line in porcelain.splitlines():
            if len(line) >= 4:
                statuses[line[3:].strip().strip('"')] = line[:2].strip()

    raw = _run(["git"] + _WS_DIFF_MODES[mode]) or ""
    parsed = _parse_unified_diff(raw)

    # untracked files: synthesize new-file diffs (only for modes that
    # show the working tree; `staged` legitimately excludes them)
    if mode != "staged":
        import os as _os
        for path, st in statuses.items():
            if st != "??":
                continue
            try:
                if _os.path.isdir(path):
                    continue           # untracked directories: not diffable
                if not _os.path.isfile(path) or _os.path.getsize(path) > 100_000:
                    parsed[path] = {"diff": f"diff --git a/{path} b/{path}\n"
                                    f"new file mode 100644\n--- /dev/null\n"
                                    f"+++ b/{path}\n@@ -0,0 +1 @@\n"
                                    "(untracked file — too large to inline)",
                                    "additions": 0, "deletions": 0,
                                    "binary": False}
                    continue
                with open(path, "r", errors="replace") as f:
                    content = f.read(20000)
                body = "".join(f"+{l}\n" for l in content.splitlines())
                parsed[path] = {
                    "diff": (f"diff --git a/{path} b/{path}\n"
                             f"new file mode 100644\n--- /dev/null\n"
                             f"+++ b/{path}\n@@ -0,0 +1,{content.count(chr(10)) + 1} @@\n"
                             + body).rstrip("\n"),
                    "additions": content.count("\n") + 1,
                    "deletions": 0, "binary": False}
            except OSError:
                continue

    files = []
    total_add = total_del = 0
    truncated = False
    budget = max_bytes
    for path in sorted(parsed):
        info = parsed[path]
        st = statuses.get(path, "M")
        if info["additions"] or info["deletions"] or st == "??":
            chunk = info["diff"][:budget]
            budget -= len(chunk)
            truncated = truncated or len(chunk) < len(info["diff"])
            files.append({"path": path, "status": st,
                          "additions": info["additions"],
                          "deletions": info["deletions"],
                          "binary": info["binary"], "diff": chunk})
            total_add += info["additions"]
            total_del += info["deletions"]
        if budget <= 0:
            truncated = True
            break

    return {"is_repo": True, "branch": branch, "mode": mode,
            "files": files,
            "summary": {"files": len(files), "additions": total_add,
                        "deletions": total_del},
            "truncated": truncated}


@app.get("/config", dependencies=[Depends(require_api_key)])
async def get_config():
    """v4.0.1 (mission §14 — GUI Settings panel): effective configuration.
    Secrets are MASKED — never returned over the wire."""
    from app.config import Config, effective_max_steps
    cfg = Config.get()
    llm = cfg.llm
    masked_key = ""
    if llm.api_key:
        k = llm.api_key
        masked_key = (k[:6] + "…" + k[-4:]) if len(k) > 12 else "****"
    return {
        "provider": llm.provider,
        "model": llm.model,
        "base_url": llm.base_url,
        "api_key": masked_key,
        "max_tokens": llm.max_tokens,
        "temperature": llm.temperature,
        # v4.3.0: the EFFECTIVE max_steps + where it came from, so the GUI
        # shows exactly what the runtime will use (transparency requirement).
        "max_steps": effective_max_steps()[0],
        "max_steps_source": effective_max_steps()[1],
        "token_budget": cfg.token_budget,
        "version": __import__("app").__version__,
        "server_api_key_enabled": bool(_API_KEY),
    }


# ─── GitHub / SHS-Code-Agent endpoints (mission §17) ─────────────────────

def _gh() -> "GitHubProvider":
    from app.git_providers.github_provider import GitHubProvider
    return GitHubProvider(repo_dir=os.getcwd())


class GitOpRequest(BaseModel):
    message: Optional[str] = None      # commit message
    branch: Optional[str] = None       # branch name
    paths: Optional[list[str]] = None  # files to add
    remote: str = "origin"


class MaxStepsRequest(BaseModel):
    """v4.3.0: user-controlled max_steps default (GUI Settings panel)."""
    value: Optional[int] = None        # None = remove override (config/default)


@app.post("/config/max-steps", dependencies=[Depends(require_api_key)])
async def set_max_steps(req: MaxStepsRequest):
    """Set (or clear) the default max_steps for FUTURE runs.

    Persists to the active config file (survives restarts) and applies to
    the live server process immediately (new agents read it at creation).
    The user decides the step budget — the runtime must respect it.
    """
    from app.config import Config, effective_max_steps
    if req.value is not None and req.value < 1:
        raise HTTPException(status_code=400,
                            detail="max_steps must be an integer >= 1")
    written = Config.get().save_max_steps(req.value)
    value, source = effective_max_steps()
    return {"max_steps": value, "max_steps_source": source,
            "persisted_to": str(written) if written else None,
            "ok": True}


class PROpRequest(BaseModel):
    repo: str                          # owner/name
    title: str
    body: str = ""
    head: str                          # source branch
    base: str = "main"
    draft: bool = False


@app.get("/github/status", dependencies=[Depends(require_api_key)])
async def github_status():
    """v4.0.1 (mission §17): SHS-Code-Agent identity + auth status +
    local repo state. Never exposes tokens."""
    try:
        st = _gh().status()
        st["local"] = {
            "branch": _gh().current_branch(),
            "dirty": bool(_gh().status_porcelain()),
        }
        return st
    except Exception as e:
        return {"error": str(e)[:300]}


@app.post("/github/commit", dependencies=[Depends(require_api_key)])
async def github_commit(req: GitOpRequest):
    """Commit local changes with SHS-Code-Agent attribution
    (Co-Authored-By trailer)."""
    if not req.message:
        raise HTTPException(status_code=400, detail="message required")
    try:
        return _gh().commit(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.post("/github/branch", dependencies=[Depends(require_api_key)])
async def github_branch(req: GitOpRequest):
    if not req.branch:
        raise HTTPException(status_code=400, detail="branch required")
    try:
        return _gh().branch(req.branch)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.post("/github/push", dependencies=[Depends(require_api_key)])
async def github_push(req: GitOpRequest):
    try:
        return _gh().push(remote=req.remote, branch=req.branch,
                          set_upstream=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.post("/github/pull", dependencies=[Depends(require_api_key)])
async def github_pull(req: GitOpRequest):
    try:
        return _gh().pull(remote=req.remote, branch=req.branch)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.post("/github/stash", dependencies=[Depends(require_api_key)])
async def github_stash(req: GitOpRequest):
    try:
        return _gh().stash(pop=bool(req.branch == "pop"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.get("/github/diff", dependencies=[Depends(require_api_key)])
async def github_diff(staged: bool = False):
    try:
        return {"diff": _gh().diff(staged=staged)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.get("/github/log", dependencies=[Depends(require_api_key)])
async def github_log(limit: int = 10):
    try:
        return {"commits": _gh().log(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.get("/github/prs", dependencies=[Depends(require_api_key)])
async def github_prs(repo: str, state: str = "open"):
    try:
        prs = _gh().list_prs(repo, state=state)
        for p in prs:
            if hasattr(p.get("state"), "value"):
                p["state"] = p["state"].value
        return {"prs": prs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.get("/github/issues", dependencies=[Depends(require_api_key)])
async def github_issues(repo: str, state: str = "open"):
    try:
        issues = _gh().list_issues(repo, state=state)
        for i in issues:
            if hasattr(i.get("state"), "value"):
                i["state"] = i["state"].value
        return {"issues": issues}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.post("/github/pr", dependencies=[Depends(require_api_key)])
async def github_create_pr(req: PROpRequest):
    try:
        return _gh().create_pr(req.repo, req.title,
                               req.body or "Created with SHS-Code",
                               req.head, req.base, draft=req.draft)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


# ─── Terminal / QA / Memory / Logs endpoints (GUI panels, mission §14) ────

class TerminalRequest(BaseModel):
    command: str
    timeout: int = 30


@app.post("/terminal/exec", dependencies=[Depends(require_api_key)])
async def terminal_exec(req: TerminalRequest):
    """v4.0.1 (mission §14 — GUI Terminal panel): run a command in the
    server's working directory. Protected by the server API key when
    configured; output is capped."""
    import subprocess as _sp
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="command required")
    try:
        proc = await asyncio.to_thread(
            _sp.run, req.command, shell=True,
            capture_output=True, text=True, timeout=max(1, min(req.timeout, 120)),
            cwd=os.getcwd())
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[:20000],
            "stderr": proc.stderr[:8000],
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)[:500]}


class QARequest(BaseModel):
    kinds: Optional[list[str]] = None
    changed_files: Optional[list[str]] = None


@app.post("/qa/verify", dependencies=[Depends(require_api_key)])
async def qa_verify(req: QARequest):
    """v4.0.1 (mission §14 — GUI QA panel): run the project-aware
    VerificationEngine (build/test/lint/typecheck)."""
    from app.verification import VerificationEngine
    try:
        engine = VerificationEngine()
        report = await engine.verify(kinds=req.kinds,
                                     changed_files=req.changed_files or [])
        return {"report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.get("/memory", dependencies=[Depends(require_api_key)])
async def memory_view():
    """v4.0.1 (mission §14 — GUI Memory panel): MEMORY.md / USER.md +
    long-term memory stats + recent entries."""
    from app.tool import memory_tool as mt
    from app.memory.long_term import LongTermMemory
    out: dict = {}
    for label, path in (("memory_md", mt.MEMORY_FILE),
                        ("user_md", mt.USER_FILE)):
        try:
            out[label] = {
                "path": str(path),
                "content": path.read_text(errors="replace")[:20000]
                           if path.exists() else "",
            }
        except Exception as e:
            out[label] = {"path": str(path), "content": "", "error": str(e)}
    try:
        ltm = LongTermMemory()
        out["long_term"] = {
            "count": await ltm.count(),
            "recent": await ltm.get_recent(10),
        }
    except Exception as e:
        out["long_term"] = {"count": 0, "recent": [], "error": str(e)[:200]}
    return out


@app.get("/logs/recent", dependencies=[Depends(require_api_key)])
async def logs_recent(lines: int = 80):
    """v4.0.1 (mission §14 — GUI Logs panel): tail of the newest log file.
    Logs are SEPARATE from the user conversation by design (mission §14)."""
    from app.logger import _LOG_DIR
    try:
        logs = sorted(_LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)
        if not logs:
            return {"file": None, "lines": []}
        newest = logs[-1]
        with open(newest, "r", errors="replace") as f:
            all_lines = f.readlines()
        return {"file": str(newest), "lines": [l.rstrip() for l in all_lines[-lines:]]}
    except Exception as e:
        return {"file": None, "lines": [], "error": str(e)[:200]}


class ModelSwitchRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


@app.post("/settings/model", dependencies=[Depends(require_api_key)])
async def switch_model(req: ModelSwitchRequest):
    """v4.0.1 (mission §14 — GUI Settings panel): switch the LLM backend.
    Persisted via Config.save_llm (0600); affects agents created after the
    switch (in-flight runs keep their backend — context is never destroyed)."""
    from app.config import Config
    from app.llm.llm import LLM
    try:
        cfg = Config.get()
        if req.base_url:
            cfg.llm.base_url = req.base_url
        if req.provider:
            cfg.llm.provider = req.provider
        if req.model:
            cfg.llm.model = req.model
        if req.api_key:
            cfg.llm.api_key = req.api_key
        Config.save_llm()
        result = await LLM().switch(
            provider=req.provider or cfg.llm.provider,
            model=req.model or cfg.llm.model,
            base_url=req.base_url or cfg.llm.base_url,
            api_key=req.api_key or cfg.llm.api_key)
        return {"switched": True, "result": {k: str(v) for k, v in result.items()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:400])


@app.get("/sessions/{session_id}/messages", dependencies=[Depends(require_api_key)])
async def get_messages(session_id: str):
    msgs = await db.get_session_messages(session_id)
    return {"session_id": session_id, "messages": msgs}


@app.get("/sessions/{session_id}/tool_calls", dependencies=[Depends(require_api_key)])
async def get_tool_calls(session_id: str):
    calls = await db.get_session_tool_calls(session_id)
    return {"session_id": session_id, "tool_calls": calls}


@app.get("/tools")
async def list_tools():
    from app.tool.base import ToolCollection
    from app.tool.python_execute import PythonExecute
    from app.tool.bash import Bash
    from app.tool.web_search import WebSearch
    from app.tool.str_replace_editor import StrReplaceEditor
    from app.tool.terminate import Terminate
    # FIX: cleanup() must be called to terminate the Bash persistent subprocess
    tools = ToolCollection(PythonExecute(), Bash(), WebSearch(), StrReplaceEditor(), Terminate())
    try:
        schemas = tools.to_openai_schemas()
        return {"tools": [{"name": s["function"]["name"], "description": s["function"]["description"]} for s in schemas]}
    finally:
        await tools.cleanup_all()


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    if _API_KEY:
        token = (
            websocket.query_params.get("api_key")
            or websocket.headers.get("x-api-key", "")
        )
        if token != _API_KEY:
            await websocket.close(code=4001)
            return

    await manager.connect(websocket, session_id)
    logger.info(f"[Server] WebSocket connected: {session_id}")
    # SHS Code FIX (registry blind spot): WS agent runs used the URL-supplied
    # session id but nothing ever created the row — messages/tool_calls were
    # orphaned and GET /sessions never showed the session. Ensure the row
    # exists (stable id) before any run.
    try:
        if await db.get_session(session_id) is None:
            await db.create_session("websocket session", agent_name="shscode",
                                    session_id=session_id)
    except Exception as e:
        logger.debug(f"[Server] WS session ensure failed: {e}")
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "session_id": session_id,
            "message": "SHS Code WebSocket ready. Send {\"prompt\": \"...\"} to start.",
        }))
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            prompt = msg.get("prompt", "").strip()
            if not prompt:
                await websocket.send_text(json.dumps({"type": "error", "message": "No prompt provided"}))
                continue

            mode_str = msg.get("mode", "build")
            mode = AgentMode.PLAN if mode_str == "plan" else AgentMode.BUILD

            # v4.0.1: agent_start is emitted by StreamingSHSCode.run itself —
            # the endpoint no longer duplicates it.

            # SHS Code FIX: coerce max_steps — a JSON string ("30") crashed the step
            # loop with TypeError ('<' not supported between str/int).
            _ms = msg.get("max_steps")
            try:
                _ms = int(_ms) if _ms is not None else None
            except (TypeError, ValueError):
                _ms = None
            streamer = StreamingSHSCode(session_id=session_id, mode=mode, max_steps=_ms)
            try:
                await streamer.run(prompt)
            except Exception as e:
                await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))

    except WebSocketDisconnect:
        manager.disconnect_one(websocket, session_id)
        logger.info(f"[Server] WebSocket disconnected: {session_id}")


class MultiAgentRequest(BaseModel):
    goal: str
    mode: str = "build"
    roles: Optional[list[str]] = None


@app.post("/multi-agent", dependencies=[Depends(require_api_key)])
async def run_multi_agent(req: MultiAgentRequest):
    from app.agent.orchestrator import MultiAgentOrchestrator
    mode = AgentMode.PLAN if req.mode.lower() == "plan" else AgentMode.BUILD
    # SHS Code FIX: req.roles was accepted but never passed — custom-role
    # requests silently got the default PM→Architect→Engineer→QA pipeline.
    # The orchestrator's SessionDB is also closed now (one open sqlite
    # connection leaked per request).
    orchestrator = MultiAgentOrchestrator(mode=mode, pipeline=req.roles)
    try:
        result = await orchestrator.run(req.goal)
    finally:
        orchestrator.db.close()
    return {"result": result}


class Team103Request(BaseModel):
    goal: str
    max_workers: int = 100


@app.post("/team103", dependencies=[Depends(require_api_key)])
async def run_team103(req: Team103Request):
    """v4.0.1: Team103 production entry over HTTP (was test-only wiring).

    Runs the 103-worker execution layer: 1 PM + 1 Architect + up to 100
    coroutine engineers + 1 QA gate. Workers share one LLM engine — they
    are NOT 103 independent model instances.
    """
    from app.v4.wiring import run_team103 as _run
    try:
        report = await _run(req.goal, max_workers=req.max_workers)
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}
    stats = getattr(report, "stats", {}) or {}
    return {
        "ok": True,
        "team_id": report.team_id,
        "merged_files": list(report.merged_files),
        "conflicts": dict(report.conflicts),
        "unresolved": [u for w in report.worker_results for u in w.unresolved],
        "avg_confidence": float(stats.get("avg_confidence", 0.0) or 0.0),
        "qa_passed": bool(report.qa_passed),
        "qa_detail": report.qa_detail,
        "duration_s": report.duration_s,
        "peak_concurrency": report.peak_concurrency,
        "pm_tasks": stats.get("pm_tasks"),
    }


# ─── Static file serving & HTML pages ─────────────────────────────────────

# Mount static files (must come before catch-all routes)
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ─── Webhook router ─────────────────────────────────────────────────────────
from app.server.webhook_router import router as webhook_router
from app.server.messaging_routes import router as messaging_router
from app import env
app.include_router(webhook_router)
app.include_router(messaging_router)
try:
    from app.secrets.router import router as secrets_router
    app.include_router(secrets_router)
except Exception as _e:
    pass  # secrets store optional; endpoints unavailable if import fails


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """Serve the built-in web chat interface."""
    chat_html = _STATIC_DIR / "chat.html"
    if chat_html.is_file():
        return HTMLResponse(content=chat_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>SHS Code WebChat</h1><p>chat.html not found.</p>")


@app.get("/gui", response_class=HTMLResponse)
async def gui_page():
    """v4.0.1 (mission §13/§14): the full SHS-Code GUI — a single-page app
    sitting on the SAME Python runtime the CLI uses (REST + structured
    WebSocket events; zero business logic duplicated client-side)."""
    gui_html = _STATIC_DIR / "gui.html"
    if gui_html.is_file():
        return HTMLResponse(content=gui_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>SHS Code GUI</h1><p>gui.html not found.</p>")


@app.get("/gui/status")
async def gui_status_check():
    # (kept distinct from the panel routes; trivial presence probe)
    return {"gui": True}


@app.get("/canvas", response_class=HTMLResponse)
async def canvas_page(session: str = "default"):
    """Serve the canvas viewer page."""
    canvas_html = _STATIC_DIR / "canvas.html"
    if canvas_html.is_file():
        return HTMLResponse(content=canvas_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>SHS Code Canvas</h1><p>canvas.html not found.</p>")


# ─── Chat WebSocket endpoint ─────────────────────────────────────────────

async def _auth_ws(websocket: WebSocket) -> bool:
    """Check WebSocket authentication. Returns True if authorized."""
    if not _API_KEY:
        return True
    token = (
        websocket.query_params.get("api_key")
        or websocket.headers.get("x-api-key", "")
    )
    return token == _API_KEY


@app.websocket("/ws/chat/{session_id}")
async def chat_websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for the built-in web chat client.

    v4.0.1 (critical wiring fix): this endpoint used to register its
    sockets ONLY in canvas_chat_manager while StreamingSHSCode emits
    through the main `manager` — the shipped chat UI therefore never
    received step/agent events. Sockets now register in BOTH registries:
    the main manager delivers the structured agent event stream, the
    canvas registry keeps viewer bookkeeping.
    """
    if not await _auth_ws(websocket):
        await websocket.close(code=4001)
        return

    await websocket.accept()

    # Register connection — main manager for agent events (v4.0.1 fix)
    manager.active.setdefault(session_id, []).append(websocket)
    # plus the canvas viewer registry (existing behaviour)
    if session_id not in canvas_chat_manager:
        # FIX: Enforce max sessions to prevent unbounded memory growth
        while len(canvas_chat_manager) >= _MAX_CANVAS_SESSIONS:
            oldest_sid, oldest_conns = canvas_chat_manager.popitem(last=False)
            for old_ws in oldest_conns:
                try:
                    await old_ws.close()
                except Exception:
                    pass
        canvas_chat_manager[session_id] = []
    canvas_chat_manager[session_id].append(websocket)

    # ensure the session row exists (same fix as /ws)
    try:
        if await db.get_session(session_id) is None:
            await db.create_session("chat session", agent_name="shscode",
                                    session_id=session_id)
    except Exception as e:
        logger.debug(f"[Server] chat session ensure failed: {e}")

    logger.info("[Server] Chat WebSocket connected: %s", session_id)

    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "session_id": session_id,
            "message": "SHS Code Chat ready. Send {\"type\": \"prompt\", \"prompt\": \"...\"} to start.",
        }))
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # Prompt message — run the agent
            prompt = msg.get("prompt", "").strip()
            if not prompt and msg_type != "prompt":
                # Unknown message type
                await websocket.send_text(json.dumps({"type": "error", "message": f"Unknown type: {msg_type}"}))
                continue

            if not prompt:
                await websocket.send_text(json.dumps({"type": "error", "message": "No prompt provided"}))
                continue

            mode_str = msg.get("mode", "build")
            mode = AgentMode.PLAN if mode_str == "plan" else AgentMode.BUILD

            # v4.0.1: agent_start is emitted by StreamingSHSCode.run itself —
            # the endpoint no longer duplicates it.

            # SHS Code FIX: coerce max_steps — a JSON string ("30") crashed the step
            # loop with TypeError ('<' not supported between str/int).
            _ms = msg.get("max_steps")
            try:
                _ms = int(_ms) if _ms is not None else None
            except (TypeError, ValueError):
                _ms = None
            streamer = StreamingSHSCode(session_id=session_id, mode=mode, max_steps=_ms)
            try:
                await streamer.run(prompt)
            except Exception as e:
                await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))

    except WebSocketDisconnect:
        logger.info("[Server] Chat WebSocket disconnected: %s", session_id)
    finally:
        manager.disconnect_one(websocket, session_id)   # v4.0.1 fix
        conns = canvas_chat_manager.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            canvas_chat_manager.pop(session_id, None)


# ─── Canvas WebSocket endpoint ──────────────────────────────────────────

@app.websocket("/ws/canvas/{session_id}")
async def canvas_websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for the live canvas viewer.

    Handles A2UI protocol messages: sync, update, clear, event.
    Delegates to CanvasServer for state management.
    """
    if not await _auth_ws(websocket):
        await websocket.close(code=4001)
        return

    canvas_srv = _get_canvas_server()

    # Use the canvas server's handler via its internal pattern
    await websocket.accept()
    # SHS Code FIX: registration now happens inside try/finally so a
    # non-WebSocketDisconnect exception no longer leaks the connection entry.

    # Register as a canvas connection
    if session_id not in canvas_chat_manager:
        # FIX: Enforce max sessions to prevent unbounded memory growth
        while len(canvas_chat_manager) >= _MAX_CANVAS_SESSIONS:
            oldest_sid, oldest_conns = canvas_chat_manager.popitem(last=False)
            for old_ws in oldest_conns:
                try:
                    await old_ws.close()
                except Exception:
                    pass
        canvas_chat_manager[session_id] = []
    canvas_chat_manager[session_id].append(websocket)

    logger.info("[Server] Canvas WebSocket connected: %s", session_id)

    # Send initial state sync
    # SHS Code FIX: get_state() used to run BEFORE the try/finally — an
    # exception there leaked the registered connection until LRU eviction.
    try:
        state = await canvas_srv.get_state(session_id)
        await websocket.send_text(json.dumps({
            "message_type": "sync",
            "session_id": session_id,
            "components": state.get("components", []),
        }))
    except Exception as exc:
        logger.error("[Server] Failed to send canvas sync: %s", exc)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "message_type": "error",
                    "error": "Invalid JSON",
                }))
                continue

            msg_type = msg.get("message_type", "")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"message_type": "pong"}))
                continue

            if msg_type == "sync":
                state = await canvas_srv.get_state(session_id)
                await websocket.send_text(json.dumps({
                    "message_type": "sync",
                    "session_id": session_id,
                    "components": state.get("components", []),
                }))
                continue

            if msg_type == "event":
                # Forward events to registered handlers
                from app.canvas.a2ui import event_from_dict
                event = event_from_dict(msg)
                logger.debug("[Server] Canvas event: %s -> %s", event.component_id, event.action)
                # Events could trigger agent actions via canvas event handlers
                continue

            # Handle update/clear from the server-side (agent → viewer is via canvas_srv.update)

    except WebSocketDisconnect:
        logger.info("[Server] Canvas WebSocket disconnected: %s", session_id)
    finally:
        conns = canvas_chat_manager.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            canvas_chat_manager.pop(session_id, None)


def serve() -> None:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="SHS Code Agent Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "app.server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
