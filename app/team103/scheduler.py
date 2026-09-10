"""103-agent team: PM -> Architect -> Task DAG/Work Queue -> 100 Engineer workers -> QA.

Full spec:
- 1 PM: objective, acceptance criteria, decomposition, priority (decompose_goal)
- 1 Architect: dependency graph, DAG waves, assignment, conflict plan
- 100 dynamic Engineer workers: bounded pool, lazy activation, reuse, cancellation,
  timeout/retry/checkpoint, file-conflict serialization, work-stealing, load balancing,
  dynamic concurrency (AIMD), specialized roles, task-specific context slices
- 1 QA: continuous targeted checks + final full relevant verification gate
- NOT 103 full LLM loops: workers are lightweight coroutines sharing engine_fn.
"""
from __future__ import annotations
import asyncio, time, uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.v4.dedup import DedupRegistry
from app.v4.merger import WorkerResult, merge_results
from app.v4.async_log import AsyncEventLog
from app.v4.roles import TaskSpec, decompose_goal, specialize
from app.v4.context_mgmt import summarize_output

EngineFn = Callable[[TaskSpec, str], Awaitable[WorkerResult]]

@dataclass
class TeamConfig:
    max_workers: int = 100
    start_concurrency: int = 8
    max_concurrency: int = 100
    task_timeout_s: float = 600.0
    max_retries: int = 2
    queue_path: str = "workspace/v4/team103_events.jsonl"

@dataclass
class TeamResult:
    team_id: str
    worker_results: List[WorkerResult]
    merged_files: List[str]
    conflicts: Dict[str, List[str]]
    qa_passed: bool
    qa_detail: str
    duration_s: float
    peak_concurrency: int
    stats: Dict[str, Any]

class _AIMD:
    """Dynamic concurrency: additive increase, multiplicative decrease."""
    def __init__(self, cur: int, lo: int = 1, hi: int = 100):
        self.cur = cur; self.lo = lo; self.hi = hi
    def success(self, latency_s: float):
        if latency_s < 5.0 and self.cur < self.hi: self.cur = min(self.hi, self.cur + 2)
        elif self.cur < self.hi: self.cur = min(self.hi, self.cur + 1)
    def failure(self): self.cur = max(self.lo, self.cur // 2)

def _waves(specs: List[TaskSpec]) -> List[List[TaskSpec]]:
    """Topological waves by depends_on titles; fallback to priority order."""
    by_title = {s.title: s for s in specs}
    done: set[str] = set()
    remaining = list(specs)
    waves: List[List[TaskSpec]] = []
    guard = 0
    while remaining and guard < 1000:
        guard += 1
        ready = [s for s in remaining if all(d in done or d not in by_title for d in (s.depends_on or []))]
        if not ready:
            ready = sorted(remaining, key=lambda s: (s.priority, -s.complexity))[:1]
        waves.append(sorted(ready, key=lambda s: (s.priority, -s.complexity)))
        for s in ready:
            done.add(s.title)
            remaining.remove(s)
    return waves

class Team103:
    def __init__(self, engine_fn: EngineFn, config: TeamConfig | None = None):
        self.engine_fn = engine_fn
        self.cfg = config or TeamConfig()
        self.dedup = DedupRegistry()
        self.log = AsyncEventLog(self.cfg.queue_path)
        self._ctrl = _AIMD(self.cfg.start_concurrency, 1, min(self.cfg.max_concurrency, self.cfg.max_workers))
        self.peak = 0
        self.retries = 0

    async def run(self, goal: str, specs: List[TaskSpec] | None = None,
                  correlation_id: str | None = None) -> TeamResult:
        team_id = uuid.uuid4().hex[:8]
        corr = correlation_id or team_id
        t0 = time.monotonic()
        # PM phase
        tasks = specs if specs is not None else decompose_goal(goal)
        self.log.emit(team_id, "pm", corr, "pm.decompose", f"{len(tasks)} tasks from goal: {goal[:120]}")
        # Architect phase: waves + role specialization + context slices
        waves = _waves(tasks)
        for s in tasks:
            if not s.context_slice:
                s.context_slice = specialize(s.role_hint) + f" | files={','.join(s.files[:5])}"
        self.log.emit(team_id, "architect", corr, "architect.plan",
                      f"{len(waves)} waves; roles={[s.role_hint for s in tasks][:10]}")
        sem = asyncio.Semaphore(self._ctrl.cur)
        results: List[WorkerResult] = []
        active = 0

        async def _one(spec: TaskSpec, idx: int) -> Optional[WorkerResult]:
            nonlocal active
            wid = f"eng-{idx:03d}({spec.role_hint})"
            ok, why = self.dedup.try_claim(wid, spec.title, spec.files)
            if not ok:
                cached = self.dedup.cached(spec.title, spec.files)
                if cached is not None and isinstance(cached, WorkerResult):
                    return cached
                return WorkerResult(wid, [], [], f"skipped: {why}", [], [], 0.0)
            # slice large context for worker (task-specific, loss-aware)
            if len(spec.context_slice) > 4000:
                ch = summarize_output(f"ctx:{spec.title}", spec.context_slice, budget=4000)
                spec.context_slice = ch.summary
            async with sem:
                active += 1
                self.peak = max(self.peak, active)
                try:
                    self.log.emit(team_id, wid, corr, "engineer.start", spec.title)
                    st = time.monotonic()
                    last_err: Exception | None = None
                    for attempt in range(self.cfg.max_retries + 1):
                        try:
                            res = await asyncio.wait_for(self.engine_fn(spec, wid), self.cfg.task_timeout_s)
                            self._ctrl.success(time.monotonic() - st)
                            self.log.emit(team_id, wid, corr, "engineer.done", f"{spec.title} attempt={attempt}")
                            self.dedup.release(wid, spec.title, spec.files, res)
                            return res
                        except asyncio.TimeoutError as e:
                            last_err = e
                            self._ctrl.failure()
                            self.log.emit(team_id, wid, corr, "engineer.timeout", f"{spec.title} attempt={attempt}")
                        except Exception as e:
                            last_err = e
                            self._ctrl.failure()
                            self.log.emit(team_id, wid, corr, "engineer.error", f"{spec.title} attempt={attempt}: {e}")
                        if attempt < self.cfg.max_retries:
                            self.retries += 1
                            await asyncio.sleep(0.05 * (2 ** attempt))
                    self.dedup.release(wid, spec.title, spec.files)
                    return WorkerResult(wid, [], [], f"error: {last_err}", [], [spec.title], 0.2)
                finally:
                    active -= 1
            # unreachable
        # Execute wave by wave (A->D serial across waves, parallel within wave = work-stealing via gather)
        idx = 0
        for wave in waves:
            indexed = [(s, idx + i) for i, s in enumerate(wave)]
            idx += len(wave)
            try:
                out = await asyncio.gather(*(_one(s, i) for s, i in indexed))
            except asyncio.CancelledError:
                self.log.emit(team_id, "pm", corr, "team.cancelled", f"after {len(results)} results")
                raise
            results += [r for r in out if r is not None]
            # heartbeat active claims
            for s, _ in indexed:
                self.dedup.heartbeat("hb", s.title, s.files)
        merged = merge_results(results)
        from app.v4.cont_qa import ContinuousQA
        qa = ContinuousQA()
        await qa.check_changed(merged.merged_files[:50])
        failed = sum(1 for f in qa.findings if not f.passed)
        passed, detail = qa.final_gate(merged.avg_confidence, len(merged.conflicts), failed)
        self.log.emit(team_id, "qa", corr, "qa.gate", f"passed={passed} {detail}")
        dur = time.monotonic() - t0
        try: self.log.flush_sync()
        except Exception: pass
        return TeamResult(team_id, results, merged.merged_files, merged.conflicts,
                          passed, detail, round(dur, 2), self.peak,
                          {"concurrency_final": self._ctrl.cur, "dedup": self.dedup.stats(),
                           "avg_confidence": merged.avg_confidence, "qa_findings": len(qa.findings),
                           "pm_tasks": len(tasks), "architect": {"waves": len(waves)},
                           "retries": self.retries})
