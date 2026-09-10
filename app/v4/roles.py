"""OPT-20: PM/Architect/Engineer/QA responsibilities (lightweight, task-specific context)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

@dataclass
class TaskSpec:
    title: str
    files: List[str] = field(default_factory=list)
    priority: int = 5
    risk: str = "low"
    subsystem: str = ""
    complexity: int = 3
    role_hint: str = "backend"
    depends_on: List[str] = field(default_factory=list)
    acceptance: str = ""
    context_slice: str = ""

ROLE_SPECIALIZATIONS = {
    "backend": "Backend engineer: APIs, services, DB, logic.",
    "frontend": "Frontend engineer: UI, components, styling.",
    "testing": "Test engineer: unit/integration/regression tests.",
    "documentation": "Docs engineer: READMEs, changelogs, comments.",
    "devops": "DevOps engineer: CI, Docker, deploy, scripts.",
    "security": "Security engineer: auth, validation, secrets.",
    "performance": "Perf engineer: caching, profiling, optimization.",
    "database": "DB engineer: schema, migrations, queries.",
}

def specialize(role_hint: str) -> str:
    return ROLE_SPECIALIZATIONS.get(role_hint, ROLE_SPECIALIZATIONS["backend"])

PM_DOC = "PM: objective, acceptance criteria, decomposition, priority."
ARCH_DOC = "Architect: architecture, dependency graph, DAG, assignment, conflicts."
ENG_DOC = "Engineer: implementation, investigation, testing, local verification."
QA_DOC = "QA: integration, regression, correctness, completion gate."

def decompose_goal(goal: str, max_tasks: int = 12) -> List[TaskSpec]:
    import re
    parts = [s.strip() for s in re.split(r"[.;\n]+", goal) if len(s.strip()) > 6][:max_tasks]
    if not parts: parts = [goal.strip()[:120]]
    specs = []
    for i, p in enumerate(parts):
        low = p.lower()
        role = "testing" if any(k in low for k in ("test","verif")) else ("documentation" if "doc" in low else "backend")
        risk = "high" if any(k in low for k in ("migrat","secur","schema")) else "low"
        specs.append(TaskSpec(title=p[:120], priority=6 if role=="testing" else 4, risk=risk, role_hint=role))
    return specs
