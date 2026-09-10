"""OPT-2: Context-aware semantic cache with invalidation + metrics.

Keys incorporate query + context fingerprint (root, branch, index epoch,
file mtimes). Stale results invalidated on git/branch/env/index change.
Similarity threshold configurable; false positives contained by requiring
exact context match + similarity >= threshold.
"""
from __future__ import annotations
import difflib, hashlib, time
from dataclasses import dataclass, field
from typing import Any, Callable
from app.v4.metrics import CacheMetrics

def fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:24]

@dataclass
class _Entry:
    value: Any
    ctx: str
    created: float
    ttl_s: float = 600.0

class SemanticCache:
    def __init__(self, threshold: float = 0.82, ttl_s: float = 600.0):
        self.threshold = threshold; self.ttl_s = ttl_s
        self._store: dict[str, _Entry] = {}
        self.metrics = CacheMetrics()
    def _sim(self, a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()
    def get(self, query: str, ctx: str) -> tuple[bool, Any]:
        t0 = time.monotonic()
        best, best_sim = None, 0.0
        for q, e in self._store.items():
            if e.ctx != ctx:
                continue
            if time.monotonic() - e.created > e.ttl_s:
                continue
            s = self._sim(query, q)
            if s > best_sim:
                best, best_sim = q, s
        if best is not None and (best == query or best_sim >= self.threshold):
            self.metrics.record_hit((time.monotonic()-t0)*1000)
            return True, self._store[best].value
        self.metrics.record_miss()
        return False, None
    def put(self, query: str, ctx: str, value: Any):
        self._store[query] = _Entry(value, ctx, time.monotonic(), self.ttl_s)
    def invalidate_ctx(self, ctx: str) -> int:
        dead = [k for k, e in self._store.items() if e.ctx == ctx]
        for k in dead: del self._store[k]
        self.metrics.record_invalidation(len(dead))
        return len(dead)
    def invalidate_all(self) -> int:
        n = len(self._store); self._store.clear()
        self.metrics.record_invalidation(n); return n
    def stats(self): return {"size": len(self._store), "threshold": self.threshold, **self.metrics.to_dict()}
