"""SHS Code — Persistence & recovery tests (spec §6-§9, §42, §43).

Verifies the full interruption-recovery loop:
  task runs → steps checkpointed → process "dies" → new process detects the
  interrupted task → /resume restores memory + injects state → continuation.
"""
import asyncio
import json
import os

import pytest

os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
    from app.state import Journal
    j = Journal(db_path=tmp_path / "home" / "state" / "journal.db")
    yield j
    j.close()


class TestTaskJournal:
    def test_task_lifecycle_events(self, journal):
        async def run():
            tid = await journal.task_start(goal="Build e-commerce site",
                                           session_id="s1", cwd="/tmp")
            await journal.record_step(tid, 1, 0, "scaffolding")
            await journal.record_action(tid, "str_replace_editor",
                                        {"path": "src/App.tsx", "command": "create"},
                                        success=True, output="created")
            await journal.record_file_change(tid, "src/App.tsx", "created")
            await journal.record_command(tid, "npm install", "ok")
            await journal.task_complete(tid)
            return tid
        tid = asyncio.run(run())

        t = asyncio.run(journal.get_task(tid))
        assert t["status"] == "completed"
        assert t["step_count"] == 1
        assert t["files_changed"][0]["path"] == "src/App.tsx"
        assert t["commands"][0]["cmd"] == "npm install"
        assert "str_replace_editor" in t["last_success"]

    def test_failure_journaling(self, journal):
        async def run():
            tid = await journal.task_start(goal="g")
            await journal.record_action(tid, "bash", {"command": "npm run build"},
                                        success=False, error="Module not found: xyz")
            await journal.task_fail(tid, "npm run build failed")
            return tid
        tid = asyncio.run(run())
        t = asyncio.run(journal.get_task(tid))
        assert t["status"] == "failed"
        # final verdict is recorded; tool-level detail lives in journal events
        assert "npm run build failed" in t["last_error"]
        evs = asyncio.run(journal.events(tid))
        tool_fail = [e for e in evs if e["kind"] == "tool_failure"]
        assert tool_fail and "Module not found" in tool_fail[0]["detail"]

    def test_progress_percent_never_fakes_completion(self, journal):
        async def run():
            tid = await journal.task_start(goal="g")
            await journal.record_progress(tid,
                                          completed=["frontend", "db"],
                                          in_progress=["cart"],
                                          pending=["checkout", "admin", "tests"])
            return tid
        tid = asyncio.run(run())
        t = asyncio.run(journal.get_task(tid))
        # 2 of 6 items (2 completed + 1 in-progress + 3 pending) → 33%;
        # and 0% when no structured progress exists — never fake completion
        assert journal.progress_percent(t) == 33
        empty = {"progress": {}}
        assert journal.progress_percent(empty) == 0

    def test_atomic_checkpoint_crash_safety(self, journal, tmp_path):
        async def run():
            tid = await journal.task_start(goal="long task")
            await journal.checkpoint(tid, 5, [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "build website"},
            ], goal="long task")
            return tid
        tid = asyncio.run(run())

        cp = asyncio.run(journal.load_checkpoint(tid))
        assert cp["step_count"] == 5
        assert len(cp["memory"]) == 2
        # checkpoint file is valid JSON (atomic write, no partial state)
        raw = (journal.checkpoint_dir / f"{tid}.json").read_text()
        assert json.loads(raw)["task_id"] == tid


class TestInterruptionRecovery:
    """Spec §42: stop → restart → /status sees it → /resume continues."""

    def test_full_interrupt_resume_cycle(self, journal):
        async def phase1():
            # Phase 1: task in progress, checkpoint saved, then "crash"
            tid = await journal.task_start(goal="Build e-commerce website",
                                           session_id="s-1", cwd="/proj")
            await journal.record_progress(tid,
                                          completed=["Project initialization",
                                                     "Database schema",
                                                     "Authentication",
                                                     "Product API",
                                                     "Frontend layout"],
                                          in_progress=["Cart API"],
                                          pending=["Checkout", "Payment integration",
                                                   "Admin dashboard", "Testing",
                                                   "Deployment"])
            await journal.record_step(tid, 12, 34, "Implementing cart API")
            await journal.record_action(tid, "str_replace_editor",
                                        {"path": "server/cart.py"},
                                        success=True, output="CartService created")
            await journal.record_action(tid, "bash",
                                        {"command": "pytest tests/test_cart.py"},
                                        success=False, error="CartController DI error")
            await journal.checkpoint(tid, 12, [
                {"role": "system", "content": "identity"},
                {"role": "user", "content": "Build e-commerce website"},
                {"role": "assistant", "content": "frontend done, cart API in progress"},
                {"role": "tool", "content": "CartService created", "tool_call_id": "t1",
                 "name": "str_replace_editor"},
            ], goal="Build e-commerce website")
            return tid
        tid = asyncio.run(phase1())

        # Phase 2: "restart" — in_progress tasks become interrupted
        n = asyncio.run(journal.mark_interrupted_running_tasks())
        assert n == 1
        t = asyncio.run(journal.last_interrupted())
        assert t["task_id"] == tid
        assert t["status"] == "interrupted"
        assert t["step_count"] == 12

        # Phase 3: /status composite shows the active task
        st = asyncio.run(journal.current_status())
        assert st["active_task"]["task_id"] == tid
        assert st["last_checkpoint_ts"] is not None

        # Phase 4: /resume restores the memory snapshot
        cp = asyncio.run(journal.load_checkpoint(tid))
        msgs = cp["memory"]
        assert len(msgs) == 4
        assert msgs[1]["content"] == "Build e-commerce website"

        # Phase 5: progress math — 5/11 = 45%, NOT "starting from scratch"
        t = asyncio.run(journal.get_task(tid))
        assert journal.progress_percent(t) == 45
        assert t["last_error"] and "CartController" in t["last_error"]

    def test_no_duplicate_checkpoint_corruption(self, journal):
        async def run():
            tid = await journal.task_start(goal="g")
            for i in range(25):
                await journal.checkpoint(tid, i, [{"role": "user", "content": f"m{i}"}])
            return tid
        tid = asyncio.run(run())
        cp = asyncio.run(journal.load_checkpoint(tid))
        assert cp["step_count"] == 24
        assert cp["memory"][0]["content"] == "m24"


class TestStateStore:
    def test_kv_layers_persist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "h"))
        from app.state import StateStore
        s = StateStore(root=tmp_path / "h" / "state")
        s.set("provider", {"active": "nvidia-nim", "model": "llama-3.1"})
        s.set("model", {"name": "llama-3.1"})
        assert s.get("provider")["active"] == "nvidia-nim"
        assert "provider" in s.keys() and "model" in s.keys()
        s.delete("model")
        assert s.get("model", "gone") == "gone"

    def test_invalid_key_rejected(self, tmp_path):
        from app.state import StateStore
        s = StateStore(root=tmp_path)
        with pytest.raises(ValueError):
            s.set("../evil", 1)


class TestConnectors:
    def test_connector_crud_and_masking(self, tmp_path):
        from app.connectors import ConnectorRegistry, mask_token
        reg = ConnectorRegistry(path=tmp_path / "c.json")
        reg.add(platform="github", username="shslab-org",
                token="ghp_supersecret123456789")
        # masked display
        shown = reg.list(masked=True)[0]["token"]
        assert "supersecret" not in shown
        # internal use gets the raw token
        assert reg.get_token("github") == "ghp_supersecret123456789"
        # persistence
        reg2 = ConnectorRegistry(path=tmp_path / "c.json")
        assert reg2.get_token("github") == "ghp_supersecret123456789"
        # disable stops supply
        reg2.set_enabled("github", False)
        assert reg2.get_token("github") is None
        assert mask_token(None) == "(not set)"

    def test_git_provider_injection(self, tmp_path, monkeypatch):
        from app.connectors import ConnectorRegistry
        from app.config import Config
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "h"))
        Config.reset()
        try:
            reg = ConnectorRegistry(path=tmp_path / "c.json")
            reg.add(platform="github", token="ghp_x", username="u")
            reg.add(platform="gitlab", token="glpat_y", username="u")
            cfg = Config.get()
            n = reg.apply_to_git_providers(cfg)
            assert n == 2
            assert cfg.git_providers.github_token == "ghp_x"
            assert cfg.git_providers.gitlab_token == "glpat_y"
        finally:
            Config.reset()


class TestSkillsEnableDisable:
    def test_persisted_disabled_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "h"))
        from app.skills.skill_engine import SkillEngine, get_skill_engine
        get_skill_engine().reload()
        engine = SkillEngine()
        names = [s.name for s in engine.list_skills()]
        assert len(names) >= 25  # 29 builtin skills
        target = names[0]
        assert engine.set_disabled(target, True) is True
        assert engine.is_disabled(target) is True
        assert target not in [s.name for s in engine.list_skills()]
        # persistence across a fresh engine
        engine2 = SkillEngine()
        assert engine2.is_disabled(target) is True
        engine2.set_disabled(target, False)
        assert target in [s.name for s in engine2.list_skills()]
