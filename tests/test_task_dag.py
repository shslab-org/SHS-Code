"""SHS Code Phase 2 — Task DAG tests (spec §6-§8).

Dependency enforcement, ready/blocked states, prioritization, persistence,
and the journal Work State 2.0 fields.
"""
import asyncio
import json

import pytest

from app.state import Journal
from app.task_dag import TaskGraph


@pytest.fixture
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
    j = Journal(tmp_path / "journal.db")
    yield j
    j.close()


class TestDependencyRules:
    def test_complete_refused_until_deps_done(self, journal):
        async def run():
            tid = await journal.task_start("build api")
            g = await TaskGraph(journal, tid).load()
            a = await g.add_node("design schema", priority=1)
            b = await g.add_node("implement api", depends_on=[a.node_id])
            ok, msg = await g.complete_node(b.node_id)
            assert ok is False
            assert "dependencies not completed" in msg
            assert b.status != "completed"
            # now complete dep, then dependent succeeds
            ok, _ = await g.complete_node(a.node_id)
            assert ok
            ok, msg = await g.complete_node(b.node_id)
            assert ok and "completed" in msg
        asyncio.run(run())

    def test_ready_and_blocked_states(self, journal):
        async def run():
            tid = await journal.task_start("x")
            g = await TaskGraph(journal, tid).load()
            a = await g.add_node("A")
            b = await g.add_node("B")
            c = await g.add_node("C", depends_on=[a.node_id, b.node_id])
            assert a.status == "ready" and b.status == "ready"
            assert c.status == "pending"  # deps exist but not completed yet
            await g.fail_node(a.node_id, "boom", retryable=False)
            assert c.status == "blocked"
            # b completed; a failed → still blocked
            await g.complete_node(b.node_id)
            assert c.status == "blocked"
            # unblocking: a becomes completed later
            a.status = "completed"
            await g.complete_node(a.node_id)
            g._recompute_statuses()
            assert c.status == "ready"
        asyncio.run(run())

    def test_fail_retryable_vs_failed(self, journal):
        async def run():
            tid = await journal.task_start("x")
            g = await TaskGraph(journal, tid).load()
            n = await g.add_node("flaky")
            await g.fail_node(n.node_id, "timeout", retryable=True)
            assert n.status == "retryable"
            assert n in g.ready_nodes()
            await g.fail_node(n.node_id, "hard error", retryable=False)
            assert n.status == "failed"
        asyncio.run(run())


class TestPrioritization:
    def test_unlock_value_orders_execution(self, journal):
        async def run():
            tid = await journal.task_start("x")
            g = await TaskGraph(journal, tid).load()
            arch = await g.add_node("architecture", priority=5)
            db = await g.add_node("database", depends_on=[arch.node_id], priority=5)
            api = await g.add_node("api", depends_on=[db.node_id], priority=1)
            tests = await g.add_node("tests", depends_on=[api.node_id], priority=6)
            order = g.prioritized_order()
            assert order[0].node_id == arch.node_id  # unlocks the chain
            await g.complete_node(arch.node_id)
            order = g.prioritized_order()
            assert order[0].node_id == db.node_id
            assert g.next_node().node_id == db.node_id
        asyncio.run(run())

    def test_priority_breaks_ties(self, journal):
        async def run():
            tid = await journal.task_start("x")
            g = await TaskGraph(journal, tid).load()
            low = await g.add_node("docs", priority=7)
            crit = await g.add_node("hotfix", priority=1)
            assert g.next_node().node_id == crit.node_id
        asyncio.run(run())

    def test_progress_percent(self, journal):
        async def run():
            tid = await journal.task_start("x")
            g = await TaskGraph(journal, tid).load()
            a = await g.add_node("A")
            b = await g.add_node("B")
            await g.add_node("C")
            await g.complete_node(a.node_id)
            await g.complete_node(b.node_id)
            assert g.progress_percent() == 66  # 2/3
        asyncio.run(run())


class TestPersistence:
    def test_graph_survives_restart(self, journal):
        async def run():
            tid = await journal.task_start("persist me")
            g = await TaskGraph(journal, tid).load()
            a = await g.add_node("step one", priority=2)
            await g.complete_node(a.node_id)
            b = await g.add_node("step two", depends_on=[a.node_id])
            await g.start_node(b.node_id)
            # "restart": fresh graph instance, same DB
            g2 = await TaskGraph(journal, tid).load()
            assert len(g2.nodes()) == 2
            assert g2.get(a.node_id).status == "completed"
            assert g2.get(b.node_id).status == "active"
            assert g2.get(a.node_id).priority == 2
        asyncio.run(run())

    def test_snapshot_roundtrip(self, journal):
        async def run():
            tid = await journal.task_start("x")
            g = await TaskGraph(journal, tid).load()
            await g.add_node("one")
            snap = g.snapshot()
            g2 = TaskGraph.from_snapshot(journal, "other-task", snap)
            assert g2.nodes()[0].title == "one"
        asyncio.run(run())

    def test_sync_to_task_mirrors_progress(self, journal):
        async def run():
            tid = await journal.task_start("mirror")
            g = await TaskGraph(journal, tid).load()
            a = await g.add_node("A")
            await g.complete_node(a.node_id)
            await g.sync_to_task()
            t = await journal.get_task(tid)
            prog = t["progress"]
            assert len(prog["completed"]) == 1
            assert len(t["plan"]) == 1  # plan column synced (deserialized)
        asyncio.run(run())

    def test_render_and_prompt(self, journal):
        async def run():
            tid = await journal.task_start("render")
            g = await TaskGraph(journal, tid).load()
            a = await g.add_node("first step", priority=2)
            await g.add_node("second step", depends_on=[a.node_id])
            await g.complete_node(a.node_id)
            r = g.render()
            assert "PLAN — 2 nodes, 50% complete" in r
            assert "NEXT:" in r
            p = g.to_prompt()
            assert "DONE" in p and "READY" in p
        asyncio.run(run())


class TestWorkState20:
    def test_phase_decisions_tests_blocked(self, journal):
        async def run():
            tid = await journal.task_start("workstate")
            await journal.set_phase(tid, "implementation")
            await journal.record_decision(tid, "use JWT", "stateless")
            await journal.record_test_result(tid, "test_auth", True)
            await journal.record_test_result(tid, "test_api", False, "500 err")
            await journal.record_recovery(tid, "fixed import", "ok")
            await journal.record_verification(tid, {"kind": "verify", "ok": True,
                                                    "summary": "build+test pass"})
            await journal.set_blocked(tid, reason="missing API key",
                                      needed="OPENAI_API_KEY",
                                      next_action="user provides key, then /resume")
            t = await journal.get_task(tid)
            assert t["phase"] == "implementation"
            assert t["decisions"][0]["decision"] == "use JWT"
            assert t["test_results"][0]["passed"] is True
            assert t["test_results"][1]["passed"] is False
            assert t["recovery_actions"][0]["action"] == "fixed import"
            assert t["verification"]["ok"] is True
            assert t["status"] == "blocked"
            assert "missing API key" in t["blocked_reason"]
        asyncio.run(run())

    def test_blocked_task_findable_for_resume(self, journal):
        async def run():
            tid = await journal.task_start("blocked task")
            await journal.set_blocked(tid, reason="needs credential")
            rows = await journal.list_tasks("blocked")
            assert rows and rows[0]["task_id"] == tid
        asyncio.run(run())
