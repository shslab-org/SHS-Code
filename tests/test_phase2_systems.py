"""SHS Code Phase 2 — Provider health, compaction, modes, profiles,
skills 2.0, subagent state tests (spec §21-§24, §23, §35-§37, §26)."""
import asyncio
import json
import time

import pytest


@pytest.fixture(autouse=True)
def _fresh_health():
    from app.provider_health import ProviderHealth
    ProviderHealth._instance = None
    yield
    ProviderHealth._instance = None


class TestProviderHealth:
    def test_record_call_and_stats(self):
        from app.provider_health import get_health
        h = get_health()
        h.record_call("nim", "llama-3", latency_s=1.2, ok=True,
                      input_tokens=1000, output_tokens=200)
        h.record_call("nim", "llama-3", latency_s=0.8, ok=True,
                      input_tokens=500, output_tokens=100)
        stats = h.stats()
        key = "nim|llama-3"
        assert key in stats
        assert stats[key]["requests"] == 2
        assert stats[key]["input_tokens"] == 1500
        assert stats[key]["latency_avg_s"] > 0
        assert stats[key]["status"] == "🟢"
        assert stats[key]["cost_estimate_usd"] is not None

    def test_rate_limit_yellow(self):
        from app.provider_health import get_health
        h = get_health()
        h.record_call("nim", "m1", latency_s=1, ok=True)
        h.record_error("nim", "m1", error="429 rate limit", rate_limited=True)
        s = h.stats()["nim|m1"]
        assert s["status"] == "🟡"
        assert s["rate_limited"] == 1
        # successful call clears rate-limit state
        h.record_call("nim", "m1", latency_s=1, ok=True)
        assert h.stats()["nim|m1"]["status"] == "🟢"

    def test_cooldown_after_hard_failures(self):
        from app.provider_health import get_health
        h = get_health()
        for _ in range(5):
            h.record_error("bad", "m", error="connection refused")
        assert h.cooldown_remaining("bad", "m") > 0
        assert not h.is_available("bad", "m")
        assert h.stats()["bad|m"]["status"] == "🔴"

    def test_recommend_provider(self):
        from app.provider_health import get_health
        h = get_health()
        for _ in range(5):
            h.record_call("good", "m", latency_s=0.5, ok=True)
        for _ in range(4):
            h.record_error("bad", "m", error="500")
        assert h.recommend_provider(["bad", "good"]) == "good"
        assert h.healthy_providers() == ["good"]

    def test_secret_masking_in_errors(self):
        from app.provider_health import get_health, _mask_error
        h = get_health()
        h.record_error("x", "m", error="auth failed for key sk-abcdef1234567890")
        s = h.stats()["x|m"]
        assert "sk-abcdef" not in s["last_error"]
        assert "[REDACTED]" in s["last_error"]
        assert "ghp_" not in _mask_error("token ghp_aaaa1111bbbb2222 leaked")

    def test_render_table(self):
        from app.provider_health import get_health
        h = get_health()
        h.record_call("nim", "llama-3", latency_s=1.0, ok=True,
                      input_tokens=10, output_tokens=5)
        out = h.render()
        assert "PROVIDER" in out and "nim" in out and "TOTAL" in out


class TestCompaction:
    def _messages(self):
        return [
            {"role": "system", "content": "You are SHS Code."},
            {"role": "user", "content": "Build JWT auth and ensure tests pass"},
            {"role": "assistant",
             "content": "I will create AuthService. Decision: use HS256. I decided to store in cookies."},
            {"role": "tool", "content": "File created at app/auth.py"},
            {"role": "tool", "content": "ERROR: ModuleNotFoundError: No module named jwt"},
            {"role": "tool", "content": "12 passed, 2 failed in 3.2s"},
            {"role": "assistant", "content": "Fixing expiry logic in app/auth.py"},
            {"role": "user", "content": "also handle refresh tokens"},
            {"role": "assistant", "content": "Refresh endpoint added to app/auth.py"},
        ]

    def test_structured_extraction(self):
        from app.compaction import extract_structured
        ex = extract_structured(self._messages()[:-2],
                                plan_text="1. auth 2. api 3. tests",
                                task_state={"phase": "impl"})
        assert any("JWT" in r for r in ex["requirements"])
        assert len(ex["decisions"]) >= 2
        assert any("jwt" in e for e in ex["errors"])
        assert any("passed" in t for t in ex["test_results"])
        assert "app/auth.py" in ex["files"]
        assert ex["plan"]

    def test_compact_preserves_head_and_recent(self):
        from app.compaction import compact_messages
        msgs = self._messages()
        new, report = compact_messages(msgs, keep_last=3,
                                       plan_text="p1", task_state={"phase": "x"})
        assert report["compacted"] is True
        assert new[0]["role"] == "system"            # identity kept
        assert new[-3:] == msgs[-3:]                  # recent verbatim
        assert len(new) < len(msgs)
        state = new[1]["content"]
        assert "IMPORTANT USER REQUIREMENTS" in state
        assert "ERRORS ENCOUNTERED" in state
        assert "TASK STATE" in state

    def test_small_context_skipped(self):
        from app.compaction import compact_messages
        new, report = compact_messages(self._messages()[:3], keep_last=6)
        assert report["compacted"] is False
        assert new == self._messages()[:3]

    def test_report_render(self):
        from app.compaction import compact_messages, render_report
        _, report = compact_messages(self._messages(), keep_last=3)
        r = render_report(report)
        assert "compacted" in r and "requirements=" in r


class TestModes:
    def test_default_is_coding(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
        from app.modes import get_active_mode, set_active_mode, get_mode_config
        assert get_active_mode() == "coding"
        assert set_active_mode("autonomous") is True
        assert get_active_mode() == "autonomous"
        cfg = get_mode_config()
        assert cfg["max_steps_scale"] == 2.0
        assert cfg["verification_level"] == "thorough"
        assert set_active_mode("nope") is False
        set_active_mode("coding")

    def test_mode_prompt_only_for_nondefault(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
        from app.modes import mode_prompt, set_active_mode
        assert mode_prompt("coding") == ""
        assert "debugging" in mode_prompt("debugging")
        set_active_mode("coding")

    def test_modes_affect_agent(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path / "h"))
        from app.modes import set_active_mode
        from app.config import Config
        Config.reset()
        set_active_mode("autonomous")
        from app.agent.manus import Manus
        agent = Manus()
        base_steps = agent._max_steps
        agent._apply_mode_and_profile()
        assert agent._max_steps == base_steps * 2   # autonomous scale
        assert agent._verification_level() == "thorough"
        assert any("MODE: autonomous" in (m.content or "")
                   for m in agent.memory.messages)
        set_active_mode("coding")


class TestAgentProfiles:
    def test_crud_and_activation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
        from app.agent_profiles import (
            create_profile, get_profile, update_profile, remove_profile,
            set_active_profile, effective_profile, list_profiles)
        create_profile("testprof", description="d",
                       system_instructions="Be a Kotlin expert",
                       skills=["android"], preferred_tools=["code_search"],
                       verification_strategy="fast")
        p = get_profile("testprof")
        assert p["skills"] == ["android"]
        update_profile("testprof", verification_strategy="thorough")
        assert get_profile("testprof")["verification_strategy"] == "thorough"
        assert set_active_profile("testprof") is True
        eff = effective_profile()
        assert eff["active"] and eff["name"] == "testprof"
        assert "Kotlin" in eff["system_instructions"]
        assert set_active_profile("") is True
        assert effective_profile()["active"] is False
        assert remove_profile("testprof") is True
        assert get_profile("testprof") is None

    def test_builtin_examples_immutable_and_seeded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
        from app.agent_profiles import list_profiles, remove_profile
        names = [p["name"] for p in list_profiles()]
        assert "android-expert" in names
        assert remove_profile("android-expert") is False  # builtin protected


class TestSkills2:
    def test_levels_and_create_remove(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
        monkeypatch.setenv("MANUSCLAW_SKILLS_DIR", str(tmp_path / "skills"))
        from app.skills.skill_engine import SkillEngine
        e = SkillEngine()
        e.create("my-custom", "custom skill", content="custom guidance")
        e2 = SkillEngine()
        s = e2.get("my-custom")
        assert s and s.level == "user"
        assert e2.remove("my-custom") is True
        assert e2.get("my-custom") is None
        # builtin immutable
        e3 = SkillEngine()
        any_builtin = e3.list_skills()[0]
        assert any_builtin.level == "builtin"
        assert e3.remove(any_builtin.name) is False

    def test_project_level_skills(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path / "h"))
        monkeypatch.setenv("MANUSCLAW_SKILLS_DIR", str(tmp_path / "h" / "skills"))
        proj = tmp_path / "proj"
        (proj / ".shscode" / "skills").mkdir(parents=True)
        (proj / ".shscode" / "skills" / "deploy.md").write_text(
            "---\nname: deploy\ndescription: project deploy skill\n---\n"
            "# deploy\nrun make deploy\n")
        import os
        old = os.getcwd()
        os.chdir(proj)
        try:
            from app.skills.skill_engine import SkillEngine
            e = SkillEngine()
            s = e.get("deploy")
            assert s and s.level == "project"
        finally:
            os.chdir(old)

    def test_install_from_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
        monkeypatch.setenv("MANUSCLAW_SKILLS_DIR", str(tmp_path / "skills"))
        src = tmp_path / "src_skill.md"
        src.write_text("---\nname: remote-skill\ndescription: installed\n---\n"
                       "# remote\n")
        from app.skills.skill_engine import SkillEngine
        e = SkillEngine()
        s = e.install(str(src))
        assert s.name == "remote-skill" and s.level == "installed"
        e2 = SkillEngine()
        assert e2.get("remote-skill") is not None
        assert e2.remove("remote-skill") is True


class TestSubagentState:
    def test_subagent_lifecycle_persisted(self, tmp_path, monkeypatch):
        async def run():
            monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path))
            from app.state import Journal
            from app.subagents import (start_subagent, finish_subagent,
                                       list_subagents, incomplete_subagents,
                                       mark_interrupted_subagents,
                                       render_subagents)
            j = Journal(tmp_path / "j.db")
            tid = await j.task_start("parent task")
            sub1 = await start_subagent(j, tid, "research auth libraries",
                                        role="researcher")
            sub2 = await start_subagent(j, tid, "write tests", role="tester")
            await finish_subagent(j, tid, sub1, output="found 3 libraries")
            rows = await list_subagents(j, tid)
            assert len(rows) == 2
            assert rows[0]["status"] == "completed"
            assert rows[0]["output"].startswith("found")
            inc = await incomplete_subagents(j, tid)
            assert [r["sub_id"] for r in inc] == [sub2]
            # crash → mark interrupted → recoverable
            n = await mark_interrupted_subagents(j, tid)
            assert n == 1
            rows = await list_subagents(j, tid)
            assert rows[1]["status"] == "interrupted"
            r = render_subagents(rows)
            assert "SUBAGENTS (2)" in r and "researcher" in r
            j.close()
        asyncio.run(run())
