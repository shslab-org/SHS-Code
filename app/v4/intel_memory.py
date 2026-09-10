"""OPT-9: Intelligent memory — classify + relevance/recency/reliability retrieval, contradiction detect, confidence."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

KINDS = {"task_state","user_preference","project_fact","architecture_fact","decision","failed_attempt","successful_pattern","dependency","constraint","todo","unresolved_issue"}

@dataclass
class MemItem:
    kind: str
    text: str
    confidence: float = 0.7
    created: float = field(default_factory=time.time)
    reliability: float = 0.7
    superseded_by: str | None = None

def classify(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("prefer","likes","wants","language:","tone")): return "user_preference"
    if any(k in t for k in ("failed","error","did not work","broken")): return "failed_attempt"
    if any(k in t for k in ("worked","success","pattern")): return "successful_pattern"
    if any(k in t for k in ("must","never","constraint","required")): return "constraint"
    if any(k in t for k in ("todo","need to","should do")): return "todo"
    if any(k in t for k in ("depends","import","requires")): return "dependency"
    if any(k in t for k in ("decided","decision","chose")): return "decision"
    if any(k in t for k in ("unresolved","open question","unknown")): return "unresolved_issue"
    if any(k in t for k in ("architec","module","component","layer")): return "architecture_fact"
    if any(k in t for k in ("project","repo","file","path")): return "project_fact"
    return "task_state"

class IntelligentMemory:
    def __init__(self): self.items: List[MemItem] = []
    def add(self, text: str, kind: str | None = None, confidence: float = 0.7, reliability: float = 0.7) -> MemItem:
        it = MemItem(kind=kind or classify(text), text=text, confidence=confidence, reliability=reliability)
        # supersede: same-kind contradictory low-confidence older items
        for old in self.items:
            if old.kind == it.kind and old.confidence < it.confidence and old.text != it.text:
                if any(w in old.text.lower() for w in ("old","previous","wrong")) or old.confidence < 0.4:
                    old.superseded_by = it.text[:80]
        self.items.append(it); return it
    def retrieve(self, query: str, kind: str | None = None, top_k: int = 5) -> List[MemItem]:
        now = time.time(); q = set(query.lower().split())
        scored = []
        for it in self.items:
            if it.superseded_by: continue
            if kind and it.kind != kind: continue
            overlap = len(q & set(it.text.lower().split()))
            recency = 1.0 / (1.0 + (now - it.created) / 3600.0)
            score = 0.5*overlap + 0.25*recency + 0.15*it.reliability + 0.1*it.confidence
            scored.append((score, it))
        scored.sort(key=lambda x: -x[0])
        return [it for _, it in scored[:top_k] if it.confidence >= 0.25]
    def contradictions(self) -> List[tuple]:
        out = []
        for i in range(len(self.items)):
            for j in range(i+1, len(self.items)):
                a, b = self.items[i], self.items[j]
                if a.kind == b.kind and a.text != b.text and abs(a.confidence-b.confidence) < 0.2:
                    out.append((a.text[:60], b.text[:60]))
        return out[:20]
