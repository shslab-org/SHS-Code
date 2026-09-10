"""OPT-3: Dependency-aware async parallel execution (A || B || C, A→B serial)."""
from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

@dataclass
class DagNode:
    id: str
    fn: Callable[[], Awaitable[Any]]
    depends_on: List[str] = field(default_factory=list)

async def run_dag(nodes: List[DagNode], timeout: float | None = None) -> Dict[str, Any]:
    by_id = {n.id: n for n in nodes}
    events = {n.id: asyncio.Event() for n in nodes}
    results: Dict[str, Any] = {}
    async def _run(n: DagNode):
        for d in n.depends_on:
            if d in events:
                await events[d].wait()
        results[n.id] = await n.fn()
        events[n.id].set()
    async def _all():
        await asyncio.gather(*(_run(n) for n in nodes))
    if timeout is None:
        await _all()
    else:
        await asyncio.wait_for(_all(), timeout)
    return results

async def run_parallel(coros: List[Awaitable[Any]], limit: int = 16) -> List[Any]:
    sem = asyncio.Semaphore(limit)
    async def _w(c):
        async with sem:
            return await c
    return list(await asyncio.gather(*(_w(c) for c in coros)))
