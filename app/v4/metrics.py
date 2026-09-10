"""Shared v4 metrics: hit/miss/stale/invalidation/latency-saved + stage timings."""
from __future__ import annotations
import time
from collections import Counter
from dataclasses import dataclass, field

@dataclass
class CacheMetrics:
    hit: int = 0
    miss: int = 0
    stale: int = 0
    invalidation: int = 0
    latency_saved_ms: float = 0.0
    def record_hit(self, saved_ms: float = 0.0):
        self.hit += 1; self.latency_saved_ms += saved_ms
    def record_miss(self): self.miss += 1
    def record_stale(self): self.stale += 1
    def record_invalidation(self, n: int = 1): self.invalidation += n
    @property
    def hit_rate(self) -> float:
        t = self.hit + self.miss
        return self.hit / t if t else 0.0
    def to_dict(self): return {"hit": self.hit, "miss": self.miss, "stale": self.stale, "invalidation": self.invalidation, "latency_saved_ms": round(self.latency_saved_ms,2), "hit_rate": round(self.hit_rate,4)}

@dataclass
class StageTimer:
    marks: dict = field(default_factory=dict)
    def measure(self, name: str):
        return _Ctx(self, name)
class _Ctx:
    def __init__(self, t: StageTimer, name: str): self.t=t; self.name=name
    def __enter__(self): self.t0=time.monotonic(); return self
    def __exit__(self, *a):
        dt=(time.monotonic()-self.t0)*1000
        self.t.marks[self.name]=self.t.marks.get(self.name,0.0)+dt
