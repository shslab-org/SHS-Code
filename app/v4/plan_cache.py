"""OPT-12: Planner overhead — cache plans, invalidate only on real change."""
from __future__ import annotations
import hashlib, time
from dataclasses import dataclass, field
from typing import Any, Dict

def _h(*parts: str) -> str:
    import hashlib
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:24]

@dataclass
class PlanCache:
    _plans: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    hits: int = 0; misses: int = 0; invalidations: int = 0
    def key(self, goal: str, project_hint: str) -> str: return _h(goal.strip(), project_hint.strip())
    def get(self, goal: str, project_hint: str, state_fingerprint: str):
        k = self.key(goal, project_hint)
        e = self._plans.get(k)
        if e and e["state"] == state_fingerprint:
            self.hits += 1; return e["plan"]
        self.misses += 1; return None
    def put(self, goal: str, project_hint: str, state_fingerprint: str, plan: Any):
        self._plans[self.key(goal, project_hint)] = {"plan": plan, "state": state_fingerprint, "at": time.time()}
    def invalidate_on(self, reason: str) -> int:
        # reasons: requirement/dependency/divergence/failure/external-state
        valid = {"requirement","dependency","divergence","failure","external"}
        if reason not in valid: return 0
        n = len(self._plans); self._plans.clear(); self.invalidations += 1
        return n
    def stats(self): return {"plans": len(self._plans), "hits": self.hits, "misses": self.misses, "invalidations": self.invalidations}
