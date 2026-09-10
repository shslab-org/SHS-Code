"""OPT-13: Risk-aware verification — low→targeted, medium→related, high→broad, milestone→full."""
from __future__ import annotations
from typing import List

def risk_of(changed_files: List[str], diff_size: int = 0, touches_core: bool = False) -> str:
    if touches_core or diff_size > 5000 or any("migrat" in f or "schema" in f for f in changed_files):
        return "high"
    if len(changed_files) > 5 or diff_size > 1000:
        return "medium"
    return "low"

def kinds_for_risk(risk: str, milestone: bool = False) -> List[str]:
    if milestone: return ["build", "test", "lint", "typecheck", "validate"]
    if risk == "low": return ["build"]  # targeted
    if risk == "medium": return ["build", "test"]
    return ["build", "test", "lint", "typecheck"]
