from __future__ import annotations

"""
SHS Code — Agent Modes (spec §36)
===================================
Configurable modes that change REAL execution behavior (never cosmetic):

  coding      — plan on, standard verification, full toolset
  debugging   — diagnosis-first prompts, fast verification loop, git+search bias
  reviewer    — review-only bias: no plan generation, code_search+verify focus
  research    — web/search bias, no build verification, plan optional
  autonomous  — high step budget, plan on, thorough verification, minimal pauses
  planning    — plan generation only, deep architecture inspection

Each mode maps to concrete knobs consumed by BaseAgent / ToolCallAgent /
Manus: plan depth, verification level, max_steps scale, tool bias hints,
system-prompt additions. The active mode persists (~/.manusclaw/mode.json)
and survives restarts.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger

_MODES: Dict[str, Dict[str, Any]] = {
    "coding": {
        "description": "default software development — plan, implement, verify",
        "plan": "llm",                 # llm | heuristic | none
        "verification_level": "standard",
        "max_steps_scale": 1.0,
        "tool_bias": ["code_search", "str_replace_editor", "verify", "bash"],
        "prompt": ("MODE: coding — implement precisely, verify before claiming done."),
    },
    "debugging": {
        "description": "failure diagnosis first — reproduce, analyze, fix, retest",
        "plan": "heuristic",
        "verification_level": "fast",
        "max_steps_scale": 1.25,
        "tool_bias": ["code_search", "bash", "verify", "project_intel"],
        "prompt": ("MODE: debugging — FIRST reproduce/diagnose (read the actual "
                   "error, locate the code with code_search), THEN form a fix "
                   "hypothesis, apply the minimal precise change, and re-verify. "
                   "Never fix blindly."),
    },
    "reviewer": {
        "description": "code review only — inspect and report, minimal edits",
        "plan": "none",
        "verification_level": "standard",
        "max_steps_scale": 0.6,
        "tool_bias": ["code_search", "project_intel", "str_replace_editor", "task_dag"],
        "prompt": ("MODE: reviewer — inspect the code (search, read, analyze "
                   "architecture) and REPORT findings: correctness, edge cases, "
                   "bugs, security, maintainability. Make edits only when a "
                   "fix is unambiguous and requested."),
    },
    "research": {
        "description": "investigation & exploration — gather, summarize, no builds",
        "plan": "heuristic",
        "verification_level": "none",
        "max_steps_scale": 1.0,
        "tool_bias": ["web_search", "crawl4ai", "code_search", "memory"],
        "prompt": ("MODE: research — investigate thoroughly, cite sources, "
                   "save findings to workspace/. Do not modify project files."),
    },
    "autonomous": {
        "description": "long-running autonomous execution — high budget, thorough verify",
        "plan": "llm",
        "verification_level": "thorough",
        "max_steps_scale": 2.0,
        "tool_bias": ["code_search", "str_replace_editor", "verify", "task_dag", "bash"],
        "prompt": ("MODE: autonomous — continue through many steps without "
                   "stopping on intermediate failures; recover, fix, re-verify. "
                   "Stop ONLY on completion or a genuine user dependency. "
                   "Keep the task_dag current at every milestone."),
    },
    "planning": {
        "description": "architecture analysis & plan production only",
        "plan": "llm",
        "verification_level": "none",
        "max_steps_scale": 0.5,
        "tool_bias": ["project_intel", "code_search", "task_dag", "ask_human"],
        "prompt": ("MODE: planning — produce a dependency-aware plan with the "
                   "task_dag tool and an architecture analysis. No implementation "
                   "unless explicitly requested."),
    },
}

def _mode_file() -> Path:
    return Path(os.getenv("MANUSCLAW_HOME",
                          str(Path.home() / ".manusclaw"))) / "mode.json"


def list_modes() -> List[Dict[str, str]]:
    return [{"name": k, "description": v["description"]}
            for k, v in _MODES.items()]


def get_mode_config(mode: Optional[str] = None) -> Dict[str, Any]:
    """Active mode's config (merged defaults). Unknown/None → coding."""
    name = (mode or get_active_mode() or "coding").lower()
    cfg = dict(_MODES.get(name, _MODES["coding"]))
    cfg["name"] = name
    return cfg


def get_active_mode() -> str:
    try:
        if _mode_file().exists():
            data = json.loads(_mode_file().read_text(encoding="utf-8"))
            m = str(data.get("mode", "coding")).lower()
            if m in _MODES:
                return m
    except Exception:
        pass
    return "coding"


def set_active_mode(mode: str) -> bool:
    if mode.lower() not in _MODES:
        return False
    try:
        _mode_file().parent.mkdir(parents=True, exist_ok=True)
        _mode_file().write_text(json.dumps({"mode": mode.lower()}, indent=1),
                              encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"[Modes] save failed: {e}")
        return False


def mode_prompt(mode: Optional[str] = None) -> str:
    """System-prompt addition injected into every run when a non-default
    mode is active (this is what makes modes affect execution, spec §36)."""
    cfg = get_mode_config(mode)
    if cfg["name"] == "coding":
        return ""
    bias = ", ".join(cfg.get("tool_bias", [])[:6])
    return (f"{cfg['prompt']}\n(preferred tools: {bias}; verification level: "
            f"{cfg['verification_level']})")


def render_modes() -> str:
    active = get_active_mode()
    lines = ["SHS Code Agent Modes (persisted, affect real execution):"]
    for name, v in _MODES.items():
        mark = "▶" if name == active else " "
        lines.append(f"  {mark} {name:<12} {v['description']}")
    lines.append(f"\nActive: {active}  —  /mode <name> to switch.")
    return "\n".join(lines)
