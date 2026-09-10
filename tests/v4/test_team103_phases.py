"""103-agent full-spec test: PM/Architect phases, dependency waves, dynamic scaling, retry, context slices."""
from __future__ import annotations
import asyncio
from app.team103 import Team103, TeamConfig
from app.v4.merger import WorkerResult
from app.v4.roles import TaskSpec

async def _eng(spec: TaskSpec, wid: str) -> WorkerResult:
    await asyncio.sleep(0.005)
    return WorkerResult(wid, [f"f_{spec.title}.py"], ["t"], f"did {spec.title} ctx={spec.context_slice[:20]}", [], [], 0.9)

def test_pm_architect_qa_phases():
    async def main():
        team = Team103(_eng, TeamConfig(max_workers=10, start_concurrency=4, task_timeout_s=10))
        specs = [TaskSpec(title="a", files=["a.py"], priority=1),
                 TaskSpec(title="b", files=["b.py"], priority=2, depends_on=["a"])]
        res = await team.run("phase test", specs)
        assert len(res.worker_results) == 2
        assert res.stats["pm_tasks"] == 2
        assert "architect" in res.stats
        assert res.peak_concurrency >= 1
    asyncio.run(main())

def test_dependency_wave_order():
    async def main():
        order = []
        async def eng(spec: TaskSpec, wid: str) -> WorkerResult:
            order.append(spec.title)
            await asyncio.sleep(0.01)
            return WorkerResult(wid, [spec.title + ".py"], [], "", [], [], 0.9)
        team = Team103(eng, TeamConfig(max_workers=10, start_concurrency=4, task_timeout_s=10))
        specs = [TaskSpec(title="child", files=["c.py"], depends_on=["parent"],
                          priority=1),
                 TaskSpec(title="parent", files=["p.py"], priority=1)]
        res = await team.run("dep test", specs)
        assert order.index("parent") < order.index("child")
    asyncio.run(main())

def test_retry_recovers_flaky():
    async def main():
        calls = {"n": 0}
        async def flaky(spec: TaskSpec, wid: str) -> WorkerResult:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("flaky once")
            return WorkerResult(wid, ["ok.py"], [], "recovered", [], [], 0.8)
        team = Team103(flaky, TeamConfig(max_workers=5, start_concurrency=2, task_timeout_s=10))
        res = await team.run("retry test", [TaskSpec(title="flaky", files=["ok.py"])])
        assert res.worker_results[0].findings == "recovered"
        assert res.stats["retries"] >= 1
    asyncio.run(main())
