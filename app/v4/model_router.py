"""OPT-11: Smart model routing — fast vs strong, benchmark vs production modes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Mode = Literal["benchmark", "production"]
Tier = Literal["fast", "strong"]

FAST_TASKS = {"summariz","index","classif","metadata","trivial","transform","bookkeep","dag","lint","format"}
STRONG_TASKS = {"architect","debug","implement","secur","verif","complex","reason"}

@dataclass
class ModelRouter:
    primary_strong: str = "bailu-2.8-free"
    fast_model: str = "bailu-2.7-free"
    fallback_strong: str = "bailu-2.7-free"
    mode: Mode = "production"
    fast_used: int = 0
    strong_used: int = 0
    def route(self, task_kind: str) -> tuple[Tier, str]:
        k = task_kind.lower()
        if self.mode == "benchmark":
            self.strong_used += 1
            return "strong", self.primary_strong  # consistency preserved
        if any(t in k for t in FAST_TASKS) and not any(t in k for t in STRONG_TASKS):
            self.fast_used += 1
            return "fast", self.fast_model
        self.strong_used += 1
        return "strong", self.primary_strong
    def stats(self): return {"mode": self.mode, "fast": self.fast_used, "strong": self.strong_used}
