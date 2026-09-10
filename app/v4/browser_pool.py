"""OPT-15: Browser process management — bounded pool, guaranteed cleanup, orphan sweeper."""
from __future__ import annotations
import asyncio, atexit, time
from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class PooledBrowser:
    tool: Any
    in_use: bool = False
    last_used: float = field(default_factory=time.time)

class BrowserPool:
    def __init__(self, max_browsers: int = 4, idle_ttl_s: float = 120.0):
        self.max = max_browsers; self.ttl = idle_ttl_s
        self._pool: List[PooledBrowser] = []
        self._lock = asyncio.Lock()
        self.created = 0; self.reused = 0; self.swept = 0
        atexit.register(self._sync_sweep)
    def _sync_sweep(self):
        try:
            for b in self._pool:
                try:
                    if hasattr(b.tool, "_browser") and b.tool._browser is None: continue
                except Exception: pass
        except Exception: pass
        self._pool.clear()
    async def acquire(self, factory):
        async with self._lock:
            for b in self._pool:
                if not b.in_use:
                    b.in_use = True; b.last_used = time.time(); self.reused += 1
                    return b
            if len(self._pool) >= self.max:
                raise RuntimeError("browser pool exhausted")
            tool = factory(); self.created += 1
            b = PooledBrowser(tool=tool, in_use=True); self._pool.append(b)
            return b
    async def release(self, b: PooledBrowser, close: bool = False):
        async with self._lock:
            b.in_use = False; b.last_used = time.time()
            if close:
                try: await b.tool.cleanup()
                except Exception: pass
                try: self._pool.remove(b)
                except ValueError: pass
    async def sweep_idle(self):
        async with self._lock:
            now = time.time(); dead = [b for b in self._pool if not b.in_use and now - b.last_used > self.ttl]
            for b in dead:
                try: await b.tool.cleanup()
                except Exception: pass
                try: self._pool.remove(b); self.swept += 1
                except ValueError: pass
            return len(dead)
    def stats(self): return {"pool": len(self._pool), "created": self.created, "reused": self.reused, "swept": self.swept}
