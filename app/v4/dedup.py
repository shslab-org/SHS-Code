"""OPT-17: Duplicate-work detection — task dedup, semantic dup, file/symbol locks, claims, ownership, stale-worker detect."""
from __future__ import annotations
import hashlib, time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:24]

@dataclass
class Claim:
    task_key: str; worker_id: str; at: float; heartbeat: float
    files: List[str] = field(default_factory=list)

class DedupRegistry:
    def __init__(self, stale_s: float = 300.0):
        self.claims: Dict[str, Claim] = {}
        self.file_owner: Dict[str, str] = {}
        self.symbol_owner: Dict[str, str] = {}
        self.result_cache: Dict[str, object] = {}
        self.stale_s = stale_s
        self.dedup_hits = 0; self.conflicts_avoided = 0
    def task_key(self, title: str, files: List[str]) -> str:
        return _h(title.strip().lower() + "\x00" + ",".join(sorted(files)))
    def try_claim(self, worker_id: str, title: str, files: List[str], symbols: List[str] | None = None) -> tuple[bool, str]:
        self._sweep_stale()
        key = self.task_key(title, files)
        if key in self.claims:
            self.dedup_hits += 1
            return False, f"duplicate of {self.claims[key].worker_id}"
        for f in files:
            if f in self.file_owner and self.file_owner[f] != worker_id:
                self.conflicts_avoided += 1
                return False, f"file-locked {f} by {self.file_owner[f]}"
        for s in (symbols or []):
            if s in self.symbol_owner and self.symbol_owner[s] != worker_id:
                self.conflicts_avoided += 1
                return False, f"symbol-locked {s}"
        self.claims[key] = Claim(key, worker_id, time.time(), time.time(), files)
        for f in files: self.file_owner[f] = worker_id
        for s in (symbols or []): self.symbol_owner[s] = worker_id
        return True, "claimed"
    def heartbeat(self, worker_id: str, title: str, files: List[str]):
        key = self.task_key(title, files)
        c = self.claims.get(key)
        if c and c.worker_id == worker_id: c.heartbeat = time.time()
    def release(self, worker_id: str, title: str, files: List[str], result: object = None):
        key = self.task_key(title, files)
        c = self.claims.pop(key, None)
        for f in files:
            if self.file_owner.get(f) == worker_id: del self.file_owner[f]
        if result is not None: self.result_cache[key] = result
    def cached(self, title: str, files: List[str]):
        return self.result_cache.get(self.task_key(title, files))
    def _sweep_stale(self):
        now = time.time()
        for k, c in list(self.claims.items()):
            if now - c.heartbeat > self.stale_s:
                del self.claims[k]
                for f in c.files:
                    if self.file_owner.get(f) == c.worker_id: del self.file_owner[f]
    def stats(self): return {"claims": len(self.claims), "files_locked": len(self.file_owner), "dedup_hits": self.dedup_hits, "conflicts_avoided": self.conflicts_avoided, "cached": len(self.result_cache)}
