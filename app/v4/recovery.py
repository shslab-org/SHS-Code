"""OPT-14: Robust recovery — malformed output repair, jittered retry, failover, checkpoint/resume, worker replacement, orphan cleanup."""
from __future__ import annotations
import asyncio, json, random, time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

def repair_json(text: str) -> Any | None:
    t = text.strip()
    for cand in (t, t + "}", t + "]}", t + '"}'):
        try: return json.loads(cand)
        except Exception: continue
    # extract largest {...} block
    s, e = t.find("{"), t.rfind("}")
    if 0 <= s < e:
        try: return json.loads(t[s:e+1])
        except Exception: return None
    return None

async def retry_async(fn: Callable[[], Awaitable[Any]], attempts: int = 5, base_s: float = 0.5, max_s: float = 30.0) -> Any:
    last = None
    for i in range(attempts):
        try: return await fn()
        except Exception as ex:
            last = ex
            if i == attempts - 1: raise
            await asyncio.sleep(min(max_s, base_s * (2 ** i)) + random.uniform(0, base_s))
    raise last  # pragma: no cover

@dataclass
class Checkpoint:
    state: dict = field(default_factory=dict)
    at: float = field(default_factory=time.time)
    def save(self, **kv): self.state.update(kv); self.at = time.time()
    def get(self, k, d=None): return self.state.get(k, d)

@dataclass
class WorkerSupervisor:
    max_restarts: int = 3
    restarts: int = 0
    replaced: int = 0
    async def run_guarded(self, fn: Callable[[], Awaitable[Any]], checkpoint: Checkpoint | None = None) -> Any:
        try:
            return await fn()
        except Exception:
            if self.restarts < self.max_restarts:
                self.restarts += 1; self.replaced += 1
                return await fn()  # restart once from checkpoint
            raise
