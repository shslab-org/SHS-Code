"""v4.0 live wiring tests: Team103 via wiring + orchestrator (OPT-17/18/19/20 live)."""
from __future__ import annotations
import asyncio
from app.v4.wiring import run_team103, get_team103
from app.v4.merger import WorkerResult
from app.v4.roles import TaskSpec

async def _eng(spec: TaskSpec, wid: str) -> WorkerResult:
    await asyncio.sleep(0.005)
    return WorkerResult(wid, [f"live_{spec.title}.py"], ["t"], f"did {spec.title}", [], [], 0.9)

def test_wiring_run_team103():
    async def main():
        specs = [TaskSpec(title=f"live-{i}", files=[f"m/f{i}.py"]) for i in range(3)]
        res = await run_team103("live wiring test", specs=specs, engine_fn=_eng,
                                max_workers=5, start_concurrency=2)
        assert len(res.worker_results) == 3
        assert res.stats["pm_tasks"] == 3
        assert res.peak_concurrency >= 1
    asyncio.run(main())

def test_wiring_dedup_skips_duplicates():
    async def main():
        specs = [TaskSpec(title="same", files=["shared.py"]) for _ in range(3)]
        res = await run_team103("dedup live", specs=specs, engine_fn=_eng, max_workers=5)
        done = [w for w in res.worker_results if "skipped" not in w.findings]
        assert len(done) == 1
        assert res.stats["dedup"]["dedup_hits"] >= 2
    asyncio.run(main())

def test_orchestrator_run_team103():
    from app.agent.orchestrator import MultiAgentOrchestrator
    async def main():
        o = MultiAgentOrchestrator()
        assert hasattr(o, "run_team103")
        specs = [TaskSpec(title="o1", files=["o1.py"]), TaskSpec(title="o2", files=["o2.py"])]
        res = await o.run_team103("orch live", specs=specs, engine_fn=_eng, max_workers=5)
        assert len(res.worker_results) == 2
    asyncio.run(main())

def test_get_team103_cached():
    t1 = get_team103(_eng, max_workers=5)
    t2 = get_team103(_eng, max_workers=5)
    assert t1 is t2
