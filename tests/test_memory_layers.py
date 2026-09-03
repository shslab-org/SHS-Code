"""Memory architecture verification (user spec §4/§5).

Four independent memory/state layers, each surviving model + provider
switching (the LLM is a replaceable reasoning engine; SHS Code state is
not owned by it):

  A. SQLite short-term memory   — session DB messages/tool calls/steps
  B. SQLite long-term memory    — workspace/.memory/long_term.db (FTS)
  C. Markdown memory            — workspace/MEMORY.md + USER.md
  D. Agent work notebook        — Journal (actions/files/commands/decisions
                                  + checkpoints + status)
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")

import pytest

from app import env


@pytest.fixture(autouse=True)
def _restore_llm_config():
    """Snapshot the global LLM config and restore it after every test —
    several tests here mutate provider/base_url/rate_limit on the live
    singleton and must never leak into other test files."""
    from app.config import Config
    llm = Config.get().llm
    snap = {k: getattr(llm, k) for k in
            ("provider", "model", "base_url", "api_key", "max_tokens",
             "temperature", "max_retries", "timeout")}
    rl = llm.rate_limit
    snap_rl = (rl.enabled, rl.rpm)
    yield
    for k, v in snap.items():
        setattr(llm, k, v)
    rl.enabled, rl.rpm = snap_rl



@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Isolated workspace directory for every layer under test."""
    monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
    return tmp_path


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if hasattr(asyncio, "get_event_loop") else asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# A. SQLite short-term memory (SessionDB)
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteShortTermMemory:
    @pytest.mark.asyncio
    async def test_messages_persist_and_reload(self, ws):
        from app.db.session import SessionDB
        db = SessionDB()
        sid = await db.create_session("short-term goal")
        await db.log_message(sid, "user", "remember this")
        await db.log_message(sid, "assistant", "noted")
        db.close()

        db2 = SessionDB()  # fresh instance, same file
        msgs = await db2.get_session_messages(sid)
        content = " ".join(str(m.get("content", "")) for m in msgs)
        assert "remember this" in content and "noted" in content
        db2.close()

    @pytest.mark.asyncio
    async def test_tool_calls_and_progress(self, ws):
        from app.db.session import SessionDB
        db = SessionDB()
        sid = await db.create_session("counting")
        await db.log_tool_call(sid, step=1, tool_name="bash",
                               args={"command": "ls"}, output="ok", error=None)
        await db.update_progress(sid, step_count=3)
        calls = await db.get_session_tool_calls(sid)
        assert any(c.get("tool_name") == "bash" for c in calls)
        s = await db.get_session(sid)
        assert s.get("step_count") == 3
        db.close()

    @pytest.mark.asyncio
    async def test_fts_search_over_messages(self, ws):
        from app.db.session import SessionDB
        db = SessionDB()
        sid = await db.create_session("searchable")
        await db.log_message(sid, "user", "unique-zeta-marker please find this")
        hits = await db.fts_search("unique-zeta-marker")
        assert hits, "FTS over session messages should find the marker"
        db.close()

    @pytest.mark.asyncio
    async def test_survives_model_switch_unharmed(self, ws):
        """Switching the LLM provider must not touch session rows."""
        from app.db.session import SessionDB
        from app.config import Config
        db = SessionDB()
        sid = await db.create_session("switch-proof")
        await db.log_message(sid, "user", "keep me")
        before = await db.get_session_messages(sid)

        cfg = Config.get()
        old = (cfg.llm.provider, cfg.llm.model)
        cfg.llm.provider, cfg.llm.model = "mock", "switched-model"
        cfg.llm.provider, cfg.llm.model = old  # restore

        after = await db.get_session_messages(sid)
        assert before == after
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# B. SQLite long-term memory
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteLongTermMemory:
    @pytest.mark.asyncio
    async def test_store_and_search(self, ws):
        from app.memory.long_term import LongTermMemory
        m = LongTermMemory()
        await m.store("User prefers Python 3.12 with uv for package management.",
                      meta={"kind": "preference"})
        await m.store("Project uses FastAPI + SQLite; no external services.",
                      meta={"kind": "project_fact"})
        hits = await m.search("package management")
        assert any("uv" in str(h.get("content", "")) for h in hits)

    @pytest.mark.asyncio
    async def test_survives_restart(self, ws):
        from app.memory.long_term import LongTermMemory
        m = LongTermMemory()
        await m.store("Architecture decision: journal-first persistence everywhere.")
        m2 = LongTermMemory()  # new instance -> same file
        hits = await m2.search("journal")
        assert any("journal-first" in str(h.get("content", "")) for h in hits)

    @pytest.mark.asyncio
    async def test_survives_model_switch(self, ws):
        from app.memory.long_term import LongTermMemory
        from app.config import Config
        m = LongTermMemory()
        await m.store("Recurring instruction: always run tests before claiming done.")
        cfg = Config.get()
        old = (cfg.llm.provider, cfg.llm.model)
        cfg.llm.provider, cfg.llm.model = "mock", "m2"
        cfg.llm.provider, cfg.llm.model = old
        hits = await m.search("always run tests")
        assert hits, "long-term memory lost after model switch simulation"


# ─────────────────────────────────────────────────────────────────────────────
# C. Markdown memory (MEMORY.md / USER.md)
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkdownMemory:
    def test_write_and_read_memory(self, ws):
        from app.tool.memory_tool import MemoryTool
        tool = MemoryTool()
        res = asyncio.run(tool.execute(action="write_memory",
                                       content="# Facts\n- prefers dark mode"))
        assert res.success
        assert (ws / "MEMORY.md").exists()
        assert "dark mode" in (ws / "MEMORY.md").read_text()

    def test_append_and_read_user(self, ws):
        from app.tool.memory_tool import MemoryTool
        tool = MemoryTool()
        asyncio.run(tool.execute(action="write_user", content="Name: SHS"))
        asyncio.run(tool.execute(action="append_memory", content="- likes concise answers"))
        res = asyncio.run(tool.execute(action="read_memory"))
        assert "concise answers" in (res.output or "")
        assert (ws / "USER.md").exists()

    def test_markdown_survives_model_switch(self, ws):
        from app.tool.memory_tool import MemoryTool
        from app.config import Config
        tool = MemoryTool()
        asyncio.run(tool.execute(action="write_memory", content="durable fact"))
        cfg = Config.get()
        old = (cfg.llm.provider, cfg.llm.model)
        cfg.llm.provider, cfg.llm.model = "mock", "switched"
        cfg.llm.provider, cfg.llm.model = old
        res = asyncio.run(tool.execute(action="read_memory"))
        assert "durable fact" in (res.output or "")

    def test_memory_file_in_configured_workspace(self, ws):
        from app.tool.memory_tool import _memory_file
        assert _memory_file().parent.resolve() == ws.resolve()


# ─────────────────────────────────────────────────────────────────────────────
# D. Agent work notebook (Journal)
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentWorkNotebook:
    @pytest.mark.asyncio
    async def test_records_what_was_done(self, ws):
        from app.state import Journal
        j = Journal(db_path=ws / ".task_queue" / "journal.db")
        tid = await j.task_start("refactor auth module", session_id="s1")
        await j.record_action(tid, "str_replace_editor",
                              {"path": "app/auth.py", "command": "edit"},
                              success=True, output="edited login()")
        await j.record_command(tid, "pytest -q", status="ran")
        await j.record_decision(tid, "use rolling window not fixed sleep")
        await j.record_file_change(tid, "app/auth.py", "edit")
        await j.record_test_result(tid, "test_login", True, "passed")
        t = await j.get_task(tid)
        assert t["goal"] == "refactor auth module"
        assert any(c.get("cmd") == "pytest -q" for c in t["commands"])
        assert any(f.get("path") == "app/auth.py" for f in t["files_changed"])
        assert any("rolling window" in d.get("decision", "") for d in t["decisions"])
        assert t["test_results"][0]["name"] == "test_login"
        evs = await j.events(tid)
        assert any(e.get("kind") == "tool_success" for e in evs)
        assert any(e.get("kind") == "file_change" for e in evs)
        j.close()

    @pytest.mark.asyncio
    async def test_checkpoint_persists_and_reloads(self, ws):
        from app.state import Journal
        j = Journal(db_path=ws / ".task_queue" / "journal.db")
        tid = await j.task_start("long task")
        await j.checkpoint(tid, step_count=42,
                            memory_messages=[{"role": "user", "content": "keep"}],
                            goal="long task", provider="mock", model="m1")
        cp = await j.load_checkpoint(tid)
        assert cp is not None and cp["step_count"] == 42
        assert cp["memory"] == [{"role": "user", "content": "keep"}]
        assert cp["provider"] == "mock"
        j.close()

        j2 = Journal(db_path=ws / ".task_queue" / "journal.db")
        cp2 = await j2.load_checkpoint(tid)
        assert cp2 is not None and cp2["step_count"] == 42
        assert cp2["memory"] == [{"role": "user", "content": "keep"}]
        j2.close()

    @pytest.mark.asyncio
    async def test_interruption_marks_and_resumes(self, ws):
        from app.state import Journal
        j = Journal(db_path=ws / ".task_queue" / "journal.db")
        tid = await j.task_start("interrupted work")
        await j.record_action(tid, "bash", {"command": "ls"},
                              success=True, output="listed")
        n = await j.mark_interrupted_running_tasks()
        assert n >= 1
        t = await j.get_task(tid)
        assert t["status"] == "interrupted"
        j.close()

    @pytest.mark.asyncio
    async def test_notebook_survives_model_switch(self, ws):
        """Work notes are journal rows — switching LLM must not touch them."""
        from app.state import Journal
        from app.config import Config
        j = Journal(db_path=ws / ".task_queue" / "journal.db")
        tid = await j.task_start("switch survival")
        await j.record_action(tid, "web_search", {"query": "x"},
                              success=True, output="found")
        before = await j.get_task(tid)

        cfg = Config.get()
        old = (cfg.llm.provider, cfg.llm.model)
        cfg.llm.provider, cfg.llm.model = "mock", "m2"
        cfg.llm.provider, cfg.llm.model = old

        after = await j.get_task(tid)
        assert before == after
        j.close()


# ─────────────────────────────────────────────────────────────────────────────
# Cross-layer: compaction must not destroy memory layers
# ─────────────────────────────────────────────────────────────────────────────

class TestCompactionPreservesMemory:
    @pytest.mark.asyncio
    async def test_all_layers_after_compaction(self, ws):
        from app.memory.long_term import LongTermMemory
        from app.compaction import compact_messages
        from app.tool.memory_tool import MemoryTool
        from app.state import Journal

        # seed every layer
        await LongTermMemory().store("fact: compaction must not destroy memory")
        tool = MemoryTool()
        await tool.execute(action="write_memory", content="md fact survives")
        j = Journal(db_path=ws / ".task_queue" / "journal.db")
        tid = await j.task_start("compaction task")
        await j.record_action(tid, "bash", {"command": "echo hi"},
                              success=True, output="hi")
        j.close()

        messages = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
        compacted, report = compact_messages(messages, keep_last=6)
        assert len(compacted) < len(messages)

        # every layer still intact
        hits = await LongTermMemory().search("compaction")
        assert any("must not destroy memory" in str(h.get("content", "")) for h in hits)
        res = await tool.execute(action="read_memory")
        assert "md fact survives" in (res.output or "")
        j2 = Journal(db_path=ws / ".task_queue" / "journal.db")
        t = await j2.get_task(tid)
        assert t["goal"] == "compaction task"
        j2.close()
