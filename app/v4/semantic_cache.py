"""OPT-2: Context-aware semantic cache with invalidation + metrics.

Keys incorporate query + context fingerprint (root, branch, index epoch,
file mtimes). Stale results invalidated on git/branch/env/index change.
Similarity threshold configurable; false positives contained by requiring
exact context match + similarity >= threshold.
"""
from __future__ import annotations
import difflib, hashlib, time
from collections import Counter
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
    qlen: int = 0
    counter: Counter = field(default_factory=Counter)

class SemanticCache:
    """FIX SPEC §4: exact O(1) fast-path + per-ctx bucket + length-bound
    prune before difflib + bounded size (LRU eviction) + thread safety.

    Semantics preserved: exact ctx match required, hit iff exact query
    or difflib ratio >= threshold, TTL expiry => miss + stale counted.
    """
    def __init__(self, threshold: float = 0.82, ttl_s: float = 600.0,
                 max_entries: int = 2000):
        self.threshold = threshold; self.ttl_s = ttl_s
        self.max_entries = max(64, int(max_entries))
        self._store: dict[tuple[str, str], _Entry] = {}
        self._by_ctx: dict[str, set[str]] = {}
        import threading as _th
        self._lock = _th.RLock()
        self.metrics = CacheMetrics()
    def _sim(self, a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()
    @staticmethod
    def _length_may_match(la: int, lb: int, threshold: float) -> bool:
        # ratio <= 2*min/(la+lb); necessary condition for ratio >= thr.
        if la == 0 or lb == 0:
            return la == lb
        return (2 * min(la, lb) / (la + lb)) >= threshold
    def get(self, query: str, ctx: str) -> tuple[bool, Any]:
        t0 = time.monotonic()
        now = time.monotonic()
        with self._lock:
            # 1) exact O(1) fast path (covers repeated code_search queries)
            e = self._store.get((ctx, query))
            if e is not None:
                if now - e.created <= e.ttl_s:
                    self.metrics.record_hit((now - t0) * 1000)
                    return True, e.value
                # stale: drop + count
                del self._store[(ctx, query)]
                qs = self._by_ctx.get(ctx)
                if qs is not None:
                    qs.discard(query)
                self.metrics.record_stale()
                self.metrics.record_miss()
                return False, None
            # 2) fuzzy: only same-ctx candidates, length-pruned difflib
            cands = self._by_ctx.get(ctx)
            if not cands:
                self.metrics.record_miss()
                return False, None
            best, best_sim, lq = None, 0.0, len(query)
            qcounter = Counter(query)
            expired: list[str] = []
            for q in list(cands):
                ent = self._store.get((ctx, q))
                if ent is None:
                    expired.append(q)
                    continue
                if now - ent.created > ent.ttl_s:
                    expired.append(q)
                    continue
                if not self._length_may_match(lq, ent.qlen or len(q), self.threshold):
                    continue
                # char-histogram upper bound (== difflib quick_ratio, but
                # reuses the precomputed per-entry Counter: ~10x cheaper
                # than building a SequenceMatcher per candidate).
                cc = ent.counter or Counter(q)
                overlap = sum((qcounter & cc).values())
                if (2 * overlap / (lq + (ent.qlen or len(q)))) < self.threshold:
                    continue
                s = self._sim(query, q)
                if s > best_sim:
                    best, best_sim = q, s
            for q in expired:
                self._store.pop((ctx, q), None)
                cands.discard(q)
                self.metrics.record_stale()
            if best is not None and best_sim >= self.threshold:
                self.metrics.record_hit((time.monotonic() - t0) * 1000)
                return True, self._store[(ctx, best)].value
            self.metrics.record_miss()
            return False, None
    def put(self, query: str, ctx: str, value: Any):
        with self._lock:
            key = (ctx, query)
            if key not in self._store and len(self._store) >= self.max_entries:
                # LRU-ish eviction: oldest created first (bounded growth,
                # the §4 slowdown root cause when cache grows unbounded).
                oldest = min(self._store.items(), key=lambda kv: kv[1].created)[0]
                self._store.pop(oldest, None)
                oc, oq = oldest
                qs = self._by_ctx.get(oc)
                if qs is not None:
                    qs.discard(oq)
            self._store[key] = _Entry(value, ctx, time.monotonic(), self.ttl_s,
                                      qlen=len(query), counter=Counter(query))
            self._by_ctx.setdefault(ctx, set()).add(query)
    def invalidate_ctx(self, ctx: str) -> int:
        with self._lock:
            qs = self._by_ctx.pop(ctx, set())
            n = 0
            for q in list(qs):
                if self._store.pop((ctx, q), None) is not None:
                    n += 1
            self.metrics.record_invalidation(n)
            return n
    def invalidate_all(self) -> int:
        with self._lock:
            n = len(self._store); self._store.clear(); self._by_ctx.clear()
            self.metrics.record_invalidation(n); return n
    def stats(self): return {"size": len(self._store), "threshold": self.threshold, "max_entries": self.max_entries, **self.metrics.to_dict()}
