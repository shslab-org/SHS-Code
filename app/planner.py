from __future__ import annotations

"""
SHS Code — Smart Task Planner (spec §7, §10, §11)
===================================================
Plan generation + persistence + exact-resume verification.

generate_plan(goal):
  - LLM mode: asks the model for a JSON plan (dependency-aware) when an
    LLM is available; validated + repaired on parse.
  - heuristic mode: numbered-steps / sentence decomposition fallback
    (always works offline).
  Both produce a TaskGraph persisted in journal.db — the plan survives
  restarts, model switches and compaction (spec §7: "the plan should be
  persisted; if the task changes, update the plan instead of losing it").

verify_resume_state(task_id) — spec §10 "Exact Resume":
  Before continuing, inspect the REAL world and compare with the stored
  checkpoint:
    1. filesystem       (do recorded files still exist / were they redone?)
    2. git state        (branch, dirty files vs checkpoint time)
    3. task state       (journal row + DAG)
    4. recent commands  (what actually ran)
  Returns a structured report: what is verified-done, what is claimed
  but missing, what changed since, and the recommended next action.

already_done_check(node_title) — spec §11 "Duplicate Work Prevention":
  Uses the Project Intelligence index to detect whether the node's target
  (file/symbol) already exists — the agent should VERIFY, not recreate.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.logger import logger
from app.task_dag import TaskGraph

# ──────────────────────────────────────────────────────────────────────────────
# Plan generation
# ──────────────────────────────────────────────────────────────────────────────

_PLAN_SYS = """You are a senior software architect. Given a development goal and a
project summary, produce a dependency-aware implementation plan.
Respond ONLY with JSON:
{"steps": [
   {"title": "short imperative step",
    "depends_on": [indices of steps this depends on, 0-based, earlier steps],
    "priority": 1-7,
    "files": ["paths likely involved"]}
 ]}
Rules: 3-12 steps. Each step must be independently verifiable. Steps that
depend on another step MUST list it. Prefer verifying existing code before
creating new code."""


def _heuristic_plan(goal: str, project_hint: str = "") -> List[Dict[str, Any]]:
    """Offline plan: decomposition from the goal text. Always available."""
    # 1. numbered list inside the goal
    numbered = re.findall(r"(?:^|\n)\s*(?:\d+[\).:]|[-*])\s+(.+)", goal)
    if 2 <= len(numbered) <= 12:
        steps = [{"title": s.strip()[:120], "depends_on": [i - 1] if i > 0 else [],
                  "priority": 5, "files": []} for i, s in enumerate(numbered)]
        return steps

    # 2. sentence decomposition
    sentences = [s.strip() for s in re.split(r"[.;\n]+", goal) if len(s.strip()) > 8]
    if len(sentences) >= 3:
        sentences = sentences[:10]
    else:
        sentences = [goal.strip()[:120]]

    # 3. standard software pipeline template
    steps: List[Dict[str, Any]] = []
    base = 0
    if project_hint:
        steps.append({"title": "Inspect project architecture (intelligence index)",
                      "depends_on": [], "priority": 2, "files": []})
        base = 1
    for s in sentences:
        title = s[:120]
        low = title.lower()
        if any(k in low for k in ("test", "verify", "check")):
            pri, dep = 6, [max(0, base)]
        elif any(k in low for k in ("fix", "bug", "debug", "repair")):
            pri, dep = 2, []
        else:
            pri, dep = 4, [max(0, base)]
        steps.append({"title": title, "depends_on": dep, "priority": pri, "files": []})
    # always finish with verification
    steps.append({"title": "Run verification (build/test) and report actual result",
                  "depends_on": [len(steps) - 1], "priority": 6, "files": []})
    return steps


def _repair_plan(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validate/normalize LLM plan JSON into safe steps."""
    steps = raw.get("steps") or raw.get("plan") or []
    if not isinstance(steps, list) or not steps:
        return []
    out: List[Dict[str, Any]] = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or s.get("step") or s.get("name") or "").strip()
        if not title:
            continue
        deps = s.get("depends_on") or []
        if isinstance(deps, (int, str)):
            deps = [deps]
        deps = [int(d) for d in deps
                if str(d).lstrip("-").isdigit() and 0 <= int(d) < i][:6]
        try:
            pri = int(s.get("priority", 5))
        except (TypeError, ValueError):
            pri = 5
        files = [str(f) for f in (s.get("files") or [])][:8]
        out.append({"title": title[:120], "depends_on": deps,
                    "priority": max(1, min(7, pri)), "files": files})
    return out[:16]


async def llm_plan(goal: str, llm, project_summary: str = "") -> Optional[List[Dict[str, Any]]]:
    """Ask the model for a plan. Returns None on any failure (caller falls back)."""
    try:
        from app.schema import Message
        prompt = f"GOAL: {goal[:1500]}\n\nPROJECT:\n{project_summary[:1200]}\n\nProduce the plan JSON now."
        resp = await llm.ask([
            Message.system(_PLAN_SYS), Message.user(prompt)])
        raw = (resp.content or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1] or [raw.strip("`")])
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(raw[start:end + 1])
        steps = _repair_plan(data)
        return steps or None
    except Exception as e:
        logger.debug(f"[Planner] LLM plan failed: {e}")
        return None


async def generate_plan(journal, task_id: str, goal: str, llm=None,
                        use_llm: bool = True) -> TaskGraph:
    """Create + persist the plan graph for a task (spec §7).
    Existing plan is UPDATED (merged), never silently lost."""
    graph = await TaskGraph(journal, task_id).load()
    project_summary = ""
    try:
        from app.intelligence import current_intelligence
        project_summary = current_intelligence().summary()
    except Exception:
        pass

    steps: Optional[List[Dict[str, Any]]] = None
    if use_llm and llm is not None:
        steps = await llm_plan(goal, llm, project_summary)
    if not steps:
        steps = _heuristic_plan(goal, project_summary)

    if graph.nodes():
        # merge: append new steps not already present
        existing = {n.title.strip().lower() for n in graph.nodes()}
        added = 0
        last_id = None
        for s in steps:
            if s["title"].strip().lower() in existing:
                continue
            node = await graph.add_node(
                s["title"], depends_on=None if last_id is None else [last_id],
                priority=s["priority"], files=s.get("files"))
            last_id = node.node_id
            added += 1
        if added:
            await graph.sync_to_task()
        return graph

    by_index: Dict[int, str] = {}
    for i, s in enumerate(steps):
        node = await graph.add_node(s["title"], priority=s["priority"],
                                    files=s.get("files"))
        by_index[i] = node.node_id
    # second pass: wire dependencies by index
    for i, s in enumerate(steps):
        nid = by_index[i]
        deps = [by_index[d] for d in s.get("depends_on") or [] if d in by_index]
        if deps:
            await graph.update_node(nid, depends_on=deps)
    await graph.sync_to_task()
    return graph


# ──────────────────────────────────────────────────────────────────────────────
# Exact resume verification (spec §10, §11)
# ──────────────────────────────────────────────────────────────────────────────

async def verify_resume_state(journal, task_id: str,
                              root: Optional[Path] = None) -> Dict[str, Any]:
    """Compare stored state with the real world. Returns a report dict:
    {verified_done, claimed_missing, changed_since, git, commands, next_action}.
    Never raises — degrades to whatever evidence is available."""
    root = Path(root or Path.cwd())
    report: Dict[str, Any] = {
        "task_id": task_id, "verified_done": [], "claimed_missing": [],
        "changed_since": [], "notes": [], "next_action": "",
    }
    try:
        task = await journal.get_task(task_id)
    except Exception:
        task = None
    if not task:
        report["notes"].append("task not found in journal")
        return report
    cp = await journal.load_checkpoint(task_id)
    cp_time = (cp or {}).get("saved_at") or 0

    # 1. filesystem vs recorded file changes
    files_changed = task.get("files_changed") or []
    for f in files_changed[-40:]:
        path = f.get("path", "")
        op = f.get("op", "modified")
        p = Path(path)
        if not p.is_absolute():
            p = root / path
        if not p.exists():
            if op in ("created", "modified"):
                report["claimed_missing"].append(f"{op} {path} — file MISSING now")
            continue
        if op in ("created", "modified"):
            if p.stat().st_mtime > (cp_time or 0):
                report["changed_since"].append(
                    f"{path} modified after last checkpoint")
            else:
                report["verified_done"].append(f"{op} {path} — present, matches checkpoint")

    # 2. git state
    git_info: Dict[str, Any] = {}
    try:
        from app.intelligence.project import git_state
        git_info = git_state(root)
    except Exception:
        pass
    report["git"] = git_info

    # 3. plan verification (claimed-complete nodes with file evidence)
    graph = await TaskGraph(journal, task_id).load()
    completed_nodes = [n for n in graph.nodes() if n.status == "completed"]
    for n in completed_nodes:
        if not n.files:
            report["verified_done"].append(f"{n.node_id}: {n.title} (recorded)")
            continue
        exists = any((root / f).exists() or Path(f).exists() for f in n.files)
        if exists:
            report["verified_done"].append(f"{n.node_id}: {n.title} ✓ files present")
        else:
            report["claimed_missing"].append(
                f"{n.node_id}: {n.title} — files missing: {', '.join(n.files[:3])}")

    # 4. commands
    commands = task.get("commands") or []
    report["commands"] = [c.get("cmd", "")[:80] for c in commands[-8:]]

    # 5. duplicate-work prevention scan (§11)
    dupes = await _detect_already_done(graph, root)
    report["already_done"] = dupes

    # 6. recommended next action
    if graph.nodes():
        nxt = graph.next_node()
        if nxt:
            report["next_action"] = f"{nxt.node_id}: {nxt.title}"
    if not report["next_action"]:
        report["next_action"] = task.get("next_action") or "continue from last checkpoint"
    return report


_GENERIC_VERBS = {
    "Inspect", "Implement", "Add", "Create", "Wire", "Write", "Build", "Fix",
    "Update", "Test", "Run", "Make", "Set", "Use", "Verify", "Check",
    "Install", "Configure", "Setup", "Set", "Get", "Put", "Remove", "Delete",
    "Refactor", "Optimize", "Review", "Analyze", "Design", "Integrate",
    "Deploy", "Prepare", "Apply", "Generate", "Extract", "Convert", "Migrate",
    "Add", "Modify", "Change", "Move", "Rename", "Split", "Merge", "Clean",
}


def _extract_targets(title: str) -> List[str]:
    """Pull candidate symbol/file names out of a step title.
    Skips generic action verbs (sentence-initial capitals are usually verbs)."""
    targets = []
    for i, m in enumerate(re.finditer(r"\b([A-Z][A-Za-z0-9_]{2,})\b", title)):
        word = m.group(1)
        if i == 0 or word in _GENERIC_VERBS:
            continue
        # require internal capital or length signal (AuthService, Auth, JWT)
        if word.isupper() and len(word) <= 5:
            targets.append(word)  # acronym like JWT, API is too generic — skip API
            if word in ("API", "UI", "DB", "CLI", "JSON", "HTTP", "URL", "HTML"):
                targets.pop()
            continue
        if not word.isupper():
            targets.append(word)
    for m in re.finditer(r"\b([\w-]+\.(?:py|js|ts|tsx|jsx|kt|java|php|go|rs|md|json|toml|yaml|yml))\b",
                         title):
        targets.append(m.group(1))
    return targets[:6]


async def _detect_already_done(graph: TaskGraph, root: Path) -> List[Dict[str, str]]:
    """For pending/ready nodes, check whether their target already exists.
    (spec §11: "Create AuthService" + existing AuthService → VERIFY, don't recreate.)"""
    out: List[Dict[str, str]] = []
    try:
        from app.intelligence import get_intelligence
        intel = get_intelligence(root)
        intel.ensure_indexed()
    except Exception:
        return out
    for n in graph.nodes():
        if n.status not in ("pending", "ready"):
            continue
        for target in _extract_targets(n.title):
            if "." in target:  # file-ish
                from app.intelligence.search import search_filename
                hits = search_filename(intel.cache, target, limit=3)
                if hits:
                    out.append({"node": n.node_id, "target": target,
                                "evidence": f"file exists: {hits[0]}",
                                "advice": "VERIFY existing file instead of recreating"})
                    break
            else:              # symbol-ish
                try:
                    hits = intel.cache.search_symbols(target, limit=3)
                except Exception:
                    hits = []
                if hits:
                    h = hits[0]
                    out.append({"node": n.node_id, "target": target,
                                "evidence": f"{h['kind']} {h['name']} at {h['path']}:{h['line']}",
                                "advice": "VERIFY existing implementation instead of recreating"})
                    break
    return out


def render_resume_report(report: Dict[str, Any]) -> str:
    """Human/LLM-readable resume report (used by /resume)."""
    lines = [f"RESUME VERIFICATION — {report.get('task_id', '?')}",
             "(stored state checked against real filesystem/git — spec §10)"]
    vd = report.get("verified_done") or []
    if vd:
        lines.append(f"VERIFIED DONE ({len(vd)}):")
        lines += [f"  ✓ {x}" for x in vd[:10]]
    cm = report.get("claimed_missing") or []
    if cm:
        lines.append(f"CLAIMED BUT MISSING ({len(cm)}):")
        lines += [f"  ✗ {x}" for x in cm[:10]]
    ch = report.get("changed_since") or []
    if ch:
        lines.append(f"CHANGED SINCE CHECKPOINT ({len(ch)}):")
        lines += [f"  ~ {x}" for x in ch[:8]]
    ad = report.get("already_done") or []
    if ad:
        lines.append("ALREADY EXISTS (do NOT recreate — verify):")
        lines += [f"  ⚠ {a['node']} {a['target']}: {a['evidence']}" for a in ad[:8]]
    g = report.get("git") or {}
    if g.get("is_repo"):
        lines.append(f"Git: {g.get('branch')} dirty={g.get('dirty_files')} last={str(g.get('last_commit', ''))[:60]}")
    cmds = report.get("commands") or []
    if cmds:
        lines.append("Recent commands: " + " | ".join(cmds[-5:]))
    lines.append(f"NEXT ACTION: {report.get('next_action', '-')}")
    return "\n".join(lines)
