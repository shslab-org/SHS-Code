"""OPT-18: Result merging — per-worker changed files/tests/findings/assumptions/issues/confidence; architect merge, conflict detect."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class WorkerResult:
    worker_id: str
    changed_files: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    findings: str = ""
    assumptions: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    confidence: float = 0.7

@dataclass
class MergeReport:
    merged_files: List[str]
    conflicts: Dict[str, List[str]]
    tests: List[str]
    unresolved: List[str]
    avg_confidence: float

def merge_results(results: List[WorkerResult]) -> MergeReport:
    owners: Dict[str, List[str]] = {}
    tests, unresolved, conf = [], [], []
    for r in results:
        conf.append(r.confidence)
        for f in r.changed_files: owners.setdefault(f, []).append(r.worker_id)
        tests += r.tests; unresolved += r.unresolved
    conflicts = {f: w for f, w in owners.items() if len(w) > 1}
    merged = sorted(owners)
    avg = sum(conf)/len(conf) if conf else 0.0
    return MergeReport(merged, conflicts, sorted(set(tests)), unresolved, round(avg, 3))
