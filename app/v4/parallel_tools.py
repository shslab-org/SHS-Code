"""OPT-4: DAG-aware parallel tool dispatch — read-only fan-out, write serialization.

Generic DAG executor (OPT-3) knows nothing about tools. This module applies
it to live tool calls: read-only calls fan out in parallel with bounded
concurrency; write/mutating calls serialize in request order to preserve
correctness. Dependency edges (A->B) force serial order even for read-only.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

READ_ONLY_HINTS = {
    "web_search", "crawl", "crawl4ai", "cross_session_search", "memory",
    "code_search", "project_intel", "browser_read", "ask_human",
}

def is_read_only(name: str, args: Dict[str, Any] | None = None) -> bool:
    if name in READ_ONLY_HINTS:
        return True
    if name in ("str_replace_editor", "editor", "file_read"):
        cmd = ((args or {}).get("command") or "").lower()
        return cmd in ("view", "read")
    return False

@dataclass
class ToolTask:
    id: str
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

async def dispatch(
    tasks: List[ToolTask],
    runner: Callable[..., Awaitable[Any]],
    limit: int = 8,
) -> Dict[str, Any]:
    """Run tool tasks: independent read-only in parallel, writes serialized.

    - Read-only tasks with satisfied deps run concurrently (semaphore limit).
    - Mutating tasks run one-at-a-time in list order.
    - depends_on edges always respected (task waits for dep results).
    - runner may be (name, args) or (name, args, task_id); 3-arg form
      avoids ambiguity when duplicate calls share name+args.
    """
    import inspect
    sem = asyncio.Semaphore(limit)
    events: Dict[str, asyncio.Event] = {t.id: asyncio.Event() for t in tasks}
    results: Dict[str, Any] = {}
    write_lock = asyncio.Lock()
    try:
        _takes_id = len(inspect.signature(runner).parameters) >= 3
    except Exception:
        _takes_id = False

    async def _call(t: ToolTask):
        if _takes_id:
            return await runner(t.name, t.args, t.id)
        return await runner(t.name, t.args)

    async def _run(t: ToolTask):
        for d in t.depends_on:
            ev = events.get(d)
            if ev is not None:
                await ev.wait()
        try:
            if is_read_only(t.name, t.args):
                async with sem:
                    results[t.id] = await _call(t)
            else:
                async with write_lock:
                    results[t.id] = await _call(t)
        finally:
            events[t.id].set()

    await asyncio.gather(*(_run(t) for t in tasks))
    return results
