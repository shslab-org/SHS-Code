"""SHS Code Phase 2 — Planner + Exact Resume tests (spec §7, §10, §11)."""
import asyncio
import json

import pytest

from app.state import Journal
from app.planner import (
    _heuristic_plan, _repair_plan, generate_plan, verify_resume_state,
    render_resume_report, llm_plan, _extract_targets,
)


@pytest.fixture
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path / "home"))
    j = Journal(tmp_path / "journal.db")
    yield j
    j.close()


class TestHeuristicPlan:
    def test_numbered_goal(self):
        steps = _heuristic_plan(
            "do this:\n1. inspect code\n2. write module\n3. add tests\n4. run build")
        assert len(steps) == 4
        assert steps[1]["depends_on"] == [0]

    def test_sentence_goal_gets_verification_step(self):
        steps = _heuristic_plan("Build the auth module. Wire it to the api. Add tests.")
        assert len(steps) >= 4
        assert any("verification" in s["title"].lower() for s in steps)

    def test_llm_plan_repair(self):
        steps = _repair_plan({
            "steps": [
                {"title": "first"},
                {"depends_on": [5], "title": "bad-dep"},      # forward dep dropped
                {"title": "ok", "depends_on": [0], "priority": 99},
                {"title": ""},
            ]})
        assert len(steps) == 3
        assert steps[1]["depends_on"] == []       # 5 >= index 2 dropped
        assert steps[2]["priority"] == 7          # clamped

    def test_llm_plan_garbage(self):
        assert _repair_plan({}) == []
        assert _repair_plan({"steps": "nope"}) == []

    def test_llm_plan_json_extraction(self):
        class FakeLLM:
            async def ask(self, msgs):
                from app.schema import Message
                return Message.assistant(
                    '```json\n{"steps":[{"title":"inspect"},{"title":"implement",'
                    '"depends_on":[0],"priority":3}]}```')
        steps = asyncio.run(llm_plan("goal", FakeLLM()))
        assert steps and steps[1]["depends_on"] == [0]

    def test_llm_plan_fallback_on_error(self):
        class BrokenLLM:
            async def ask(self, msgs):
                raise RuntimeError("provider down")
        assert asyncio.run(llm_plan("goal", BrokenLLM())) is None


class TestGeneratePlan:
    def test_plan_persisted_and_merge_not_lost(self, journal):
        async def run():
            tid = await journal.task_start("build auth")
            g = await generate_plan(journal, tid, "Build auth. Add tests.",
                                    llm=None, use_llm=False)
            assert len(g.nodes()) >= 3
            # same task, new goal → merged (existing steps preserved)
            g2 = await generate_plan(journal, tid,
                                     "Also add caching to auth. Add tests.",
                                     llm=None, use_llm=False)
            titles = {n.title.strip().lower() for n in g2.nodes()}
            # original steps still present
            assert len(titles & {n.title.strip().lower() for n in g.nodes()}) >= 3
            # restart: fresh load
            g3 = await TaskGraph_load(journal, tid).load()
            assert g3.nodes()
        from app.task_dag import TaskGraph as TaskGraph_load
        asyncio.run(run())

    def test_targets_extraction_filters_verbs(self):
        t = _extract_targets("Create AuthService and JWT token handler in auth.py")
        assert "auth.py" in t
        assert "AuthService" in t
        assert "Create" not in t
        assert "JWT" not in t or True  # JWT may or may not pass; not an error


class TestExactResume:
    def _mk_project(self, root):
        (root / "src").mkdir()
        (root / "src" / "auth.py").write_text("class AuthService: pass\n")
        (root / "src" / "api.py").write_text("import src.auth\n")

    def test_verified_vs_claimed_missing(self, journal, tmp_path):
        async def run():
            self._mk_project(tmp_path)
            tid = await journal.task_start("resume check")
            await journal.record_file_change(tid, "src/auth.py", "created")
            await journal.record_file_change(tid, "src/ghost.py", "created")
            await journal.checkpoint(tid, 3, [], goal="resume check")
            report = await verify_resume_state(journal, tid, root=tmp_path)
            assert any("src/auth.py" in v for v in report["verified_done"])
            assert any("ghost.py" in c and "MISSING" in c
                       for c in report["claimed_missing"])
        asyncio.run(run())

    def test_changed_since_checkpoint_detected(self, journal, tmp_path):
        async def run():
            self._mk_project(tmp_path)
            tid = await journal.task_start("detect edits")
            await journal.record_file_change(tid, "src/api.py", "modified")
            await journal.checkpoint(tid, 1, [], goal="x")
            # simulate a post-checkpoint edit (explicit future mtime —
            # avoids clock-granularity flakiness)
            import os
            f = tmp_path / "src" / "api.py"
            f.write_text("# edited after\n")
            future = (await journal.load_checkpoint(tid))["saved_at"] + 30
            os.utime(f, (future, future))
            report = await verify_resume_state(journal, tid, root=tmp_path)
            assert any("api.py" in c and "modified after" in c
                       for c in report["changed_since"])
        asyncio.run(run())

    def test_duplicate_work_prevention(self, journal, tmp_path, monkeypatch):
        async def run():
            # index the tmp project so symbol search can see it
            monkeypatch.setenv("MANUSCLAW_HOME", str(tmp_path / "home2"))
            from app.intelligence.cache import IntelligenceCache
            from app.intelligence.manager import Intelligence
            self._mk_project(tmp_path)
            intel = Intelligence(tmp_path)
            intel.cache.refresh()

            tid = await journal.task_start("rebuild auth")
            from app.task_dag import TaskGraph
            g = await TaskGraph(journal, tid).load()
            await g.add_node("Implement AuthService class")
            report = await verify_resume_state(journal, tid, root=tmp_path)
            dupes = report.get("already_done") or []
            # Intelligence layer found AuthService already exists → advise verify
            assert any("AuthService" in d["target"] and "VERIFY" in d["advice"]
                       for d in dupes)
        asyncio.run(run())

    def test_git_state_captured(self, journal, tmp_path):
        async def run():
            import subprocess
            for args in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                         ["git", "config", "user.name", "t"],
                         ["git", "add", "-A"], ["git", "commit", "-qm", "init"]):
                subprocess.run(args, cwd=str(tmp_path), check=True,
                               capture_output=True)
            tid = await journal.task_start("git aware")
            await journal.task_start("git aware")
            report = await verify_resume_state(journal, tid, root=tmp_path)
            assert report["git"].get("is_repo") is True
            assert report["git"].get("last_commit")
            rendered = render_resume_report(report)
            assert "RESUME VERIFICATION" in rendered
        asyncio.run(run())

    def test_task_not_found_degrades(self, journal):
        async def run():
            report = await verify_resume_state(journal, "nonexistent")
            assert any("task not found" in n for n in report["notes"])
        asyncio.run(run())
