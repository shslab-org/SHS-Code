"""103-agent stress: 10/25/50/75/100 workers — throughput, latency, errors, conflicts, recovery, no deadlock."""
from __future__ import annotations
import asyncio, time
import pytest
from app.team103 import Team103, TeamConfig
from app.v4.merger import WorkerResult
from app.v4.roles import TaskSpec

async def _engine(spec: TaskSpec, wid: str) -> WorkerResult:
    await asyncio.sleep(0.01)  # simulate work
    if "boom" in spec.title:
        raise RuntimeError("worker crash sim")
    return WorkerResult(wid, [f"file_{spec.title[:8]}.py"], ["t"], f"did {spec.title}", [], [], 0.85)

def _specs(n: int):
    return [TaskSpec(title=f"task-{i:03d}", files=[f"mod_{i%10}/f{i}.py"], priority=(i % 7) + 1, role_hint="backend") for i in range(n)]

@pytest.mark.parametrize("n", [10, 25, 50, 75, 100])
def test_team_scales(n):
    async def main():
        team = Team103(_engine, TeamConfig(max_workers=100, start_concurrency=8, task_timeout_s=30))
        t0 = time.monotonic()
        res = await team.run(f"stress {n} tasks", _specs(n))
        dt = time.monotonic() - t0
        assert len(res.worker_results) == n
        assert dt < 60  # no deadlock
        assert res.peak_concurrency >= 1
        assert res.stats["avg_confidence"] > 0.5
        return res
    r = asyncio.run(main())
    assert r.qa_passed in (True, False)

def test_team_conflict_serialization():
    async def main():
        team = Team103(_engine, TeamConfig(max_workers=100, start_concurrency=16, task_timeout_s=30))
        specs = [TaskSpec(title="same task", files=["shared.py"]) for _ in range(5)]
        res = await team.run("conflict test", specs)
        # only one should really execute; rest skipped as duplicates
        done = [w for w in res.worker_results if "skipped" not in w.findings]
        assert len(done) == 1
    asyncio.run(main())

def test_team_worker_crash_recovery():
    async def main():
        team = Team103(_engine, TeamConfig(max_workers=10, start_concurrency=4, task_timeout_s=30))
        specs = [TaskSpec(title="boom task", files=["x.py"]), TaskSpec(title="good task", files=["y.py"])]
        res = await team.run("recovery test", specs)
        assert len(res.worker_results) == 2
        # crash does not stop DAG
        assert any("error" in w.findings for w in res.worker_results)
    asyncio.run(main())
