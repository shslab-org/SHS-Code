"""OPT-7: Background prefetch/indexing — incremental, never full reindex inline."""
from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

@dataclass
class PrefetchStats:
    runs: int = 0
    last_ms: float = 0.0
    items: int = 0

class BackgroundPrefetcher:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self.stats = PrefetchStats()
        self._cache: dict[str, Any] = {}
    def start(self, jobs: dict[str, Callable[[], Any]]):
        if self._task and not self._task.done():
            return
        async def _run():
            t0 = time.monotonic()
            for k, fn in jobs.items():
                try:
                    self._cache[k] = await asyncio.to_thread(fn)
                except Exception as e:
                    self._cache[k] = {"error": str(e)}
            self.stats.runs += 1
            self.stats.items = len(jobs)
            self.stats.last_ms = (time.monotonic()-t0)*1000
        self._task = asyncio.create_task(_run())
    async def wait(self, timeout: float = 30.0):
        if self._task:
            try: await asyncio.wait_for(asyncio.shield(self._task), timeout)
            except asyncio.TimeoutError: pass
    def get(self, key: str, default=None): return self._cache.get(key, default)
    def snapshot(self): return dict(self._cache)
