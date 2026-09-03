from __future__ import annotations

"""
SHS Code — Custom Agent Profiles (spec §37)
=============================================
User-defined specialized agent profiles composed from:
  system instructions   (extra prompt)
  skills                (names to force-inject)
  preferred tools       (tool bias list)
  model preference      (provider/model hint for /model)
  verification strategy (none|fast|standard|thorough)

Persisted at ~/.shscode/profiles.json — survives restarts. Applied at
agent construction (SHSCode accepts profile kwargs), and via /profile use.
Builtin examples are seeded on first run and fully editable.
"""

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger
from app import env

def _profiles_path() -> Path:
    return env.home_dir() / "profiles.json"

_VALID_VERIFICATION = {"none", "fast", "standard", "thorough"}

_BUILTIN_EXAMPLES: Dict[str, Dict[str, Any]] = {
    "android-expert": {
        "description": "Android/Kotlin/Gradle specialist",
        "system_instructions": (
            "You are operating as an Android specialist: Kotlin, Jetpack "
            "Compose, Gradle, ADB. Prefer ./gradlew assembleDebug builds, "
            "minSdk/targetSdk awareness, and AndroidManifest checks."),
        "skills": ["android", "kotlin", "gradle"],
        "preferred_tools": ["code_search", "str_replace_editor", "verify", "bash"],
        "model_preference": "",
        "verification_strategy": "standard",
        "builtin": True,
    },
    "backend-expert": {
        "description": "APIs, databases, backend services",
        "system_instructions": (
            "You are operating as a backend specialist: APIs, databases, "
            "auth, performance. Inspect schema before queries; validate "
            "migrations; test endpoints end-to-end."),
        "skills": ["python", "sql", "api"],
        "preferred_tools": ["code_search", "str_replace_editor", "verify", "python_execute"],
        "model_preference": "",
        "verification_strategy": "standard",
        "builtin": True,
    },
    "frontend-expert": {
        "description": "Web UI, components, styling",
        "system_instructions": (
            "You are operating as a frontend specialist: React/Vue/TS, "
            "components, accessibility, visual correctness. Verify with "
            "typecheck + build; inspect rendered output where possible."),
        "skills": ["web-dev", "javascript", "typescript", "ui-ux"],
        "preferred_tools": ["code_search", "str_replace_editor", "node_execute", "verify"],
        "model_preference": "",
        "verification_strategy": "standard",
        "builtin": True,
    },
    "security-reviewer": {
        "description": "adversarial security review",
        "system_instructions": (
            "You are operating as a security reviewer: hunt injection, auth "
            "bypass, secret leaks, unsafe deserialization, path traversal. "
            "REPORT findings with file:line; never fix silently."),
        "skills": ["security", "api"],
        "preferred_tools": ["code_search", "project_intel", "bash"],
        "model_preference": "",
        "verification_strategy": "none",
        "builtin": True,
    },
    "devops-expert": {
        "description": "CI/CD, containers, deployment",
        "system_instructions": (
            "You are operating as a DevOps specialist: Docker, CI pipelines, "
            "releases. Validate configs before applying; never break a "
            "working pipeline without a rollback plan."),
        "skills": ["linux", "automation", "git"],
        "preferred_tools": ["bash", "code_search", "verify"],
        "model_preference": "",
        "verification_strategy": "fast",
        "builtin": True,
    },
}


def _load_all() -> Dict[str, Dict[str, Any]]:
    data: Dict[str, Dict[str, Any]] = {}
    try:
        if _profiles_path().exists():
            data = json.loads(_profiles_path().read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"[Profiles] load failed: {e}")
    # seed builtin examples once
    changed = False
    for k, v in _BUILTIN_EXAMPLES.items():
        if k not in data:
            data[k] = v
            changed = True
    if changed:
        _save_all(data)
    return data


def _save_all(data: Dict[str, Dict[str, Any]]) -> None:
    try:
        _profiles_path().parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(_profiles_path().parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _profiles_path())
    except Exception as e:
        logger.error(f"[Profiles] save failed: {e}")


def _active_path() -> Path:
    return _profiles_path().parent / "active_profile.json"


def get_active_profile_name() -> str:
    try:
        if _active_path().exists():
            return json.loads(_active_path().read_text(encoding="utf-8")).get("profile", "")
    except Exception:
        pass
    return ""


def set_active_profile(name: str) -> bool:
    if not name:
        try:
            _active_path().unlink(missing_ok=True)
            return True
        except Exception:
            return False
    if name not in _load_all():
        return False
    try:
        _active_path().parent.mkdir(parents=True, exist_ok=True)
        _active_path().write_text(json.dumps({"profile": name}), encoding="utf-8")
        return True
    except Exception:
        return False


def list_profiles() -> List[Dict[str, Any]]:
    data = _load_all()
    active = get_active_profile_name()
    out = []
    for name, p in sorted(data.items()):
        p2 = dict(p)
        p2["name"] = name
        p2["active"] = (name == active)
        out.append(p2)
    return out


def get_profile(name: str) -> Optional[Dict[str, Any]]:
    return _load_all().get(name)


def create_profile(name: str, description: str = "",
                   system_instructions: str = "",
                   skills: Optional[List[str]] = None,
                   preferred_tools: Optional[List[str]] = None,
                   model_preference: str = "",
                   verification_strategy: str = "standard") -> Dict[str, Any]:
    name = name.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):
        raise ValueError(f"invalid profile name: {name!r}")
    if verification_strategy not in _VALID_VERIFICATION:
        raise ValueError(f"verification_strategy must be one of {sorted(_VALID_VERIFICATION)}")
    data = _load_all()
    profile = {
        "description": description[:300],
        "system_instructions": system_instructions[:3000],
        "skills": [str(s) for s in (skills or [])][:12],
        "preferred_tools": [str(t) for t in (preferred_tools or [])][:15],
        "model_preference": model_preference[:100],
        "verification_strategy": verification_strategy,
        "builtin": False,
        "created_at": time.time(),
    }
    data[name] = profile
    _save_all(data)
    return profile


def update_profile(name: str, **changes: Any) -> Optional[Dict[str, Any]]:
    data = _load_all()
    p = data.get(name)
    if not p:
        return None
    for k in ("description", "system_instructions", "model_preference"):
        if k in changes and changes[k] is not None:
            p[k] = str(changes[k])[:3000 if k == "system_instructions" else 300]
    for k in ("skills", "preferred_tools"):
        if k in changes and changes[k] is not None:
            p[k] = [str(x) for x in changes[k]][:15]
    if changes.get("verification_strategy"):
        vs = str(changes["verification_strategy"])
        if vs not in _VALID_VERIFICATION:
            raise ValueError(f"verification_strategy must be one of {sorted(_VALID_VERIFICATION)}")
        p["verification_strategy"] = vs
    data[name] = p
    _save_all(data)
    return p


def remove_profile(name: str) -> bool:
    data = _load_all()
    p = data.get(name)
    if not p or p.get("builtin"):
        return False
    del data[name]
    _save_all(data)
    if get_active_profile_name() == name:
        set_active_profile("")
    return True


def effective_profile() -> Dict[str, Any]:
    """Active profile resolved to concrete settings (empty = defaults)."""
    name = get_active_profile_name()
    if not name:
        return {"name": "", "active": False, "system_instructions": "",
                "skills": [], "preferred_tools": [], "model_preference": "",
                "verification_strategy": ""}
    p = get_profile(name) or {}
    return {"name": name, "active": True,
            "system_instructions": p.get("system_instructions", ""),
            "skills": p.get("skills") or [],
            "preferred_tools": p.get("preferred_tools") or [],
            "model_preference": p.get("model_preference", ""),
            "verification_strategy": p.get("verification_strategy", "standard")}


def render_profiles() -> str:
    rows = list_profiles()
    if not rows:
        return "No profiles defined. /profile create <name> [description]"
    lines = ["SHS Code Agent Profiles:"]
    for p in rows:
        mark = "▶" if p.get("active") else " "
        tag = " (builtin example)" if p.get("builtin") else ""
        lines.append(f"  {mark} {p['name']:<22} {p.get('description', '')[:48]}{tag}")
        if p.get("skills"):
            lines.append(f"      skills: {', '.join(p['skills'][:8])}")
        if p.get("verification_strategy") and p.get("verification_strategy") != "standard":
            lines.append(f"      verification: {p['verification_strategy']}")
        if p.get("model_preference"):
            lines.append(f"      model pref: {p['model_preference']}")
    lines.append("\n/profile use <name> | off   — activate/deactivate")
    return "\n".join(lines)
