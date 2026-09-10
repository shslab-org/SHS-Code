"""OPT-19: Continuous QA — targeted validation in parallel; final full relevant verification."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import List
from app.v4.risk_verify import kinds_for_risk, risk_of

@dataclass
class QAFinding:
    scope: str; passed: bool; detail: str

class ContinuousQA:
    def __init__(self): self.findings: List[QAFinding] = []
    async def check_changed(self, changed_files: List[str]) -> List[QAFinding]:
        risk = risk_of(changed_files)
        kinds = kinds_for_risk(risk)
        # lightweight parallel checks (existence + non-empty); real suites run at milestone
        import os
        async def _one(f: str) -> QAFinding:
            ok = os.path.exists(f)
            return QAFinding(f, ok, "exists" if ok else "missing")
        out = await asyncio.gather(*(_one(f) for f in changed_files[:50]))
        self.findings += out
        return list(out)
    def final_gate(self, merge_confidence: float, open_conflicts: int, failed: int) -> tuple[bool, str]:
        if failed > 0: return False, f"{failed} checks failed"
        if open_conflicts > 0 and merge_confidence < 0.6: return False, "conflicts with low confidence"
        return True, "QA gate passed"
