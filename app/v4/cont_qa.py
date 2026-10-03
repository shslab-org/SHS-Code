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
        # lightweight parallel checks; real suites run at milestone.
        # v4.0.1 (mission §3): a claimed changed file must exist AND be
        # non-empty — a 0-byte "created" file is a failed check, not a
        # passed one. Previously bare existence passed QA.
        import os
        async def _one(f: str) -> QAFinding:
            try:
                ok = os.path.exists(f) and os.path.getsize(f) > 0
                detail = "exists, non-empty" if ok else (
                    "missing" if not os.path.exists(f) else "exists but EMPTY")
            except OSError as e:
                ok, detail = False, f"stat failed: {e}"
            return QAFinding(f, ok, detail)
        out = await asyncio.gather(*(_one(f) for f in changed_files[:50]))
        self.findings += out
        return list(out)
    def final_gate(self, merge_confidence: float, open_conflicts: int, failed: int) -> tuple[bool, str]:
        if failed > 0: return False, f"{failed} checks failed"
        if open_conflicts > 0 and merge_confidence < 0.6: return False, "conflicts with low confidence"
        # v4.0.1: low aggregate confidence is itself a QA failure — a merge
        # of partial/failed workers (avg conf < 0.5) must not pass the gate.
        if merge_confidence < 0.5: return False, f"low merge confidence ({merge_confidence:.2f})"
        return True, "QA gate passed"
