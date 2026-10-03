"""v4.0.1 streaming + session-kind regression tests.

Covers:
1. UniversalClient._post_stream SSE parsing — content deltas, split
   tool-call fragments, usage, [DONE] handling, error statuses.
2. LLM.ask_tool(on_delta=...) end-to-end against a live local SSE server.
3. SessionDB message kinds — interim narration excluded from replay,
   returned by the full-message endpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Local OpenAI-compatible SSE server
# ──────────────────────────────────────────────────────────────────────────────

class _SSEScenario:
    """Scripted SSE chunks the fake provider will emit."""

    def __init__(self, chunks, status=200, usage_in_final=True):
        self.chunks = chunks
        self.status = status
        self.usage_in_final = usage_in_final


def _make_chunk(delta, finish=None, usage=None):
    payload: dict = {"id": "chatcmpl-x", "object": "chat.completion.chunk",
                     "model": "test-model", "choices": []}
    if delta is not None or finish:
        payload["choices"] = [{"index": 0, "delta": delta or {}, "finish_reason": finish}]
    if usage is not None:
        payload["usage"] = usage
    return payload


async def _run_sse_server(scenario: _SSEScenario):
    """Start a local aiohttp server that streams the scenario. Returns
    (base_url, server_task)."""
    from aiohttp import web

    calls = {"payloads": []}

    async def handler(request):
        body = await request.json()
        calls["payloads"].append(body)
        if not body.get("stream"):
            # non-streaming request → plain JSON response
            return web.json_response({
                "choices": [{"message": {"role": "assistant",
                                         "content": "plain answer"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "total_tokens": 2}})
        resp = web.StreamResponse(status=scenario.status,
                                  headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        if scenario.status == 200:
            for chunk in scenario.chunks:
                await resp.write(
                    f"data: {json.dumps(chunk)}\n\n".encode())
                await asyncio.sleep(0.001)
            await resp.write(b"data: [DONE]\n\n")
        else:
            await resp.write(json.dumps({"error": "boom"}).encode())
        return resp

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return f"http://127.0.0.1:{port}/v1", runner, calls


# ──────────────────────────────────────────────────────────────────────────────
# 1. SSE parsing
# ──────────────────────────────────────────────────────────────────────────────

class TestUniversalClientStreaming:
    @pytest.mark.asyncio
    async def test_content_and_split_tool_calls(self):
        from app.llm.llm import UniversalClient
        scenario = _SSEScenario([
            _make_chunk({"role": "assistant", "content": "Let me "}),
            _make_chunk({"content": "check the tests."}),
            # tool call split across 4 fragments, index 0 — name itself
            # split across two fragments (some backends do this)
            _make_chunk({"tool_calls": [{"index": 0, "id": "call-1",
                                         "type": "function",
                                         "function": {"name": "ba", "arguments": "{\"comm"}}]}),
            _make_chunk({"tool_calls": [{"index": 0,
                                         "function": {"name": "sh"}}]}),
            _make_chunk({"tool_calls": [{"index": 0,
                                         "function": {"arguments": "and\": \"echo hi\"}"}}]}),
            _make_chunk({}, finish="tool_calls"),
            _make_chunk(None, usage={"prompt_tokens": 10, "completion_tokens": 5,
                                     "total_tokens": 15}),
        ])
        base, runner, _ = await _run_sse_server(scenario)
        try:
            client = UniversalClient(base, "sk-test", "test-model")
            got: list[str] = []
            data = await client.chat(
                [{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "bash",
                                                         "parameters": {}}}],
                on_delta=got.append)
            assert "".join(got) == "Let me check the tests."
            msg = data["choices"][0]["message"]
            assert msg["content"] == "Let me check the tests."
            assert msg["tool_calls"][0]["id"] == "call-1"
            assert msg["tool_calls"][0]["function"]["name"] == "bash"
            args = json.loads(msg["tool_calls"][0]["function"]["arguments"])
            assert args == {"command": "echo hi"}
            assert data["usage"]["total_tokens"] == 15
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            await client.cleanup()
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_no_delta_no_stream_flag(self):
        """Without on_delta the request must NOT set stream:true."""
        from app.llm.llm import UniversalClient
        scenario = _SSEScenario([_make_chunk({"content": "plain"})])
        base, runner, calls = await _run_sse_server(scenario)
        try:
            client = UniversalClient(base, "sk-test", "test-model")
            data = await client.chat([{"role": "user", "content": "hi"}])
            # non-streaming path: the fake server still replies with SSE
            # chunks (it's a stub) — what matters is stream flag absence.
            assert calls["payloads"][0].get("stream") is None
            await client.cleanup()
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_rate_limit_raises(self):
        from app.llm.llm import UniversalClient
        from app.exceptions import RateLimitError
        scenario = _SSEScenario([], status=429)
        base, runner, _ = await _run_sse_server(scenario)
        try:
            client = UniversalClient(base, "sk-test", "test-model")
            with pytest.raises(RateLimitError):
                await client.chat([{"role": "user", "content": "hi"}],
                                  on_delta=lambda s: None)
            await client.cleanup()
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_400_falls_back_to_non_streaming(self):
        """A backend that rejects streaming must transparently fall back."""
        from app.llm.llm import UniversalClient
        # 400 with SSE content type; the non-streaming path re-requests and
        # gets... also 400 — but the fallback must at least attempt the
        # plain call. We assert the ValueError path by making the SECOND
        # (non-stream) response valid via a toggling server.
        from aiohttp import web
        state = {"n": 0}

        async def handler(request):
            body = await request.json()
            state["n"] += 1
            if body.get("stream"):
                return web.json_response({"error": "streaming unsupported"},
                                         status=400)
            return web.json_response({
                "choices": [{"message": {"role": "assistant",
                                         "content": "fallback answer"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2,
                          "total_tokens": 3}})
        app = web.Application()
        app.router.add_post("/v1/chat/completions", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            client = UniversalClient(f"http://127.0.0.1:{port}/v1",
                                     "sk-test", "test-model")
            got: list[str] = []
            data = await client.chat([{"role": "user", "content": "hi"}],
                                     on_delta=got.append)
            assert data["choices"][0]["message"]["content"] == "fallback answer"
            await client.cleanup()
        finally:
            await runner.cleanup()


# ──────────────────────────────────────────────────────────────────────────────
# 2. LLM.ask_tool on_delta plumbing
# ──────────────────────────────────────────────────────────────────────────────

class TestLLMDeltaPlumbing:
    @pytest.mark.asyncio
    async def test_ask_tool_streams_deltas(self, monkeypatch):
        from app.llm.llm import LLM, UniversalClient
        scenario = _SSEScenario([
            _make_chunk({"role": "assistant", "content": "Hello "}),
            _make_chunk({"content": "world."}),
            _make_chunk({}, finish="stop"),
        ])
        base, runner, _ = await _run_sse_server(scenario)
        try:
            llm = LLM.__new__(LLM)  # bypass config-driven init
            llm._provider = "universal"
            llm._model = "test-model"
            llm._backend = UniversalClient(base, "sk-test", "test-model")
            llm.token_budget = __import__(
                "app.llm.token_tracker", fromlist=["TokenBudget"]).TokenBudget(
                max_tokens=100000)
            llm._pool = None
            llm._fallback_models = lambda: []          # type: ignore
            llm._limiter = lambda: None                # type: ignore
            llm._set_backend_model = lambda m: None    # type: ignore
            from app.schema import Message
            got: list[str] = []
            msg = await llm.ask_tool(
                [Message.user("say hello")],
                tools=[{"type": "function", "function": {"name": "bash",
                                                         "parameters": {}}}],
                on_delta=got.append)
            assert msg.content == "Hello world."
            assert "".join(got) == "Hello world."
            await llm.cleanup_backend()
        finally:
            await runner.cleanup()


# ──────────────────────────────────────────────────────────────────────────────
# 3. SessionDB message kinds
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionMessageKinds:
    @pytest.mark.asyncio
    async def test_interim_excluded_from_replay(self, tmp_path):
        from app.db.session import SessionDB
        db = SessionDB(db_path=tmp_path / "s.db")
        try:
            sid = await db.create_session("test")
            await db.log_message(sid, "user", "build the feature")
            await db.log_message(sid, "assistant", "Let me check the file.", kind="interim")
            await db.log_message(sid, "assistant", "The feature is built.")
            replay = await db.get_messages(sid, limit=10)
            contents = [m["content"] for m in replay]
            assert "Let me check the file." not in contents
            assert "The feature is built." in contents
            assert "build the feature" in contents
            # full endpoint returns EVERYTHING with kind visible
            full = await db.get_session_messages(sid)
            kinds = {m["content"]: m["kind"] for m in full}
            assert kinds["Let me check the file."] == "interim"
            assert kinds["The feature is built."] == "final"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_kind_migration_on_old_db(self, tmp_path):
        """A database created BEFORE the kind column must auto-migrate."""
        import sqlite3
        from app.db.session import SessionDB
        raw = tmp_path / "old.db"
        conn = sqlite3.connect(raw)
        conn.executescript("""
            CREATE TABLE sessions (id TEXT PRIMARY KEY, goal TEXT, agent_name TEXT,
                mode TEXT DEFAULT 'build', parent_session_id TEXT, started_at REAL,
                ended_at REAL, state TEXT DEFAULT 'running', step_count INTEGER DEFAULT 0,
                error TEXT, compressed INTEGER DEFAULT 0);
            CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT, role TEXT, content TEXT, ts REAL);
        """)
        conn.execute("INSERT INTO messages (session_id, role, content, ts)"
                     " VALUES ('s1', 'user', 'legacy row', 1.0)")
        conn.commit()
        conn.close()
        db = SessionDB(db_path=raw)
        try:
            # touching the DB triggers the migration
            sid = await db.create_session("migrated")
            await db.log_message(sid, "assistant", "new row")
            full = await db.get_session_messages(sid)
            assert any(m["kind"] == "final" for m in full)
        finally:
            db.close()
