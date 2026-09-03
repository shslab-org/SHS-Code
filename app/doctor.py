from __future__ import annotations

"""
SHS Code — Diagnostics (/doctor)  (spec §45)
Detects common problems and prints actionable diagnostics.
Every check returns (name, ok, detail, hint).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Tuple
from app import env

Check = Tuple[str, bool, str, str]

_HOME = env.home_dir()


def _check_python() -> Check:
    ok = sys.version_info >= (3, 10)
    return (
        "python",
        ok,
        f"{sys.version.split()[0]} at {sys.executable}",
        "SHS Code requires Python 3.10+" if not ok else "",
    )


def _check_deps() -> Check:
    missing = []
    for mod, pip_name in [
        ("rich", "rich"), ("prompt_toolkit", "prompt_toolkit"),
        ("pydantic", "pydantic"), ("aiohttp", "aiohttp"),
        ("yaml", "pyyaml"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    ok = not missing
    return (
        "dependencies",
        ok,
        "all core deps present" if ok else f"missing: {', '.join(missing)}",
        f"pip install {' '.join(missing)}" if missing else "",
    )


def _check_provider() -> Check:
    try:
        from app.config import Config
        cfg = Config.get()
        p = cfg.llm.provider
        model = cfg.llm.model
        if p == "mock":
            return ("provider", False, "provider is 'mock' (no real LLM configured)",
                    "Set [llm] provider/model/api_key in ~/.shscode/config.yaml, "
                    "or use /provider <name> / /provider add ...")
        key = bool(cfg.llm.api_key) or p in ("ollama", "gguf")
        if not key:
            return ("provider", False, f"provider {p!r} has no api_key",
                    f"Set the API key env var or /provider set {p} --api-key ...")
        return ("provider", True, f"provider={p} model={model}", "")
    except Exception as e:
        return ("provider", False, f"config load failed: {e}",
                "Fix ~/.shscode/config.yaml syntax")


def _check_registry_files() -> Check:
    problems = []
    for name, path in [
        ("providers.json", _HOME / "providers.json"),
        ("connectors.json", _HOME / "connectors.json"),
    ]:
        if path.exists():
            try:
                import json
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                problems.append(f"{name}: corrupt ({e})")
    if not (_HOME / "state").exists() or not (_HOME / "state" / "journal.db").exists():
        problems.append("journal.db not created yet (empty history — normal on first run)")
    ok = not any("corrupt" in p for p in problems)
    return ("state files", ok, "; ".join(problems) or "journal + registries OK",
            "Delete the corrupt file to regenerate" if not ok else "")


def _check_journal() -> Check:
    try:
        from app.state import Journal
        j = Journal.get()
        with j._rl:
            j._connection().execute("SELECT COUNT(*) FROM tasks").fetchone()
        return ("journal", True, f"journal OK at {j.db_path}", "")
    except Exception as e:
        return ("journal", False, f"journal broken: {e}",
                "Remove ~/.shscode/state/journal.db (history will reset)")


def _check_skills() -> Check:
    try:
        from app.skills.skill_engine import get_skill_engine
        skills = get_skill_engine().list_skills()
        return ("skills", True, f"{len(skills)} skill(s) loaded", "")
    except Exception as e:
        return ("skills", False, f"skill engine failed: {e}",
                "Check ~/.shscode/skills for broken markdown files")


def _check_mcp() -> Check:
    try:
        from app.config import Config
        servers = Config.get().mcp_servers
        if not servers:
            return ("mcp", True, "no MCP servers configured", "")
        lines = []
        for s in servers:
            has = bool(s.url or (s.command and shutil.which(s.command)))
            lines.append(f"{s.name}: {'ok' if has else 'command/url missing'}")
        ok = all("ok" in l for l in lines)
        return ("mcp", ok, "; ".join(lines),
                "Fix mcp_servers entries in config" if not ok else "")
    except Exception as e:
        return ("mcp", False, f"config error: {e}", "")


def _check_git() -> Check:
    git = shutil.which("git")
    if not git:
        return ("git", False, "git not found on PATH", "Install git")
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=10)
        if branch.returncode == 0:
            return ("git", True, f"git at {git}, branch: {branch.stdout.strip() or 'detached'}", "")
        return ("git", True, f"git at {git} (not in a repo)", "")
    except Exception:
        return ("git", True, f"git at {git}", "")


def _check_fs_writable() -> Check:
    for d in (_HOME, _HOME / "state", _HOME / "checkpoints"):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("ok")
            probe.unlink()
        except Exception as e:
            return ("filesystem", False, f"{d} not writable: {e}",
                    "Fix permissions on ~/.shscode")
    return ("filesystem", True, f"{_HOME} writable", "")


def _check_connectors() -> Check:
    try:
        from app.connectors import get_connectors
        cons = get_connectors().list(masked=True)
        if not cons:
            return ("connectors", True, "no connectors configured", "")
        bad = [c["platform"] for c in cons if not c.get("enabled")]
        return ("connectors", True,
                f"{len(cons)} connector(s): {', '.join(c['platform'] for c in cons)}"
                + (f" (disabled: {', '.join(bad)})" if bad else ""), "")
    except Exception as e:
        return ("connectors", False, f"connectors.json problem: {e}", "")


def _check_rate_limit() -> Check:
    try:
        from app.llm.rate_limiter import all_stats, detect_nim
        from app.config import Config
        cfg = Config.get()
        rl = getattr(cfg.llm, "rate_limit", None)
        stats = all_stats()
        nim = detect_nim(cfg.llm.base_url, cfg.llm.provider)
        detail = f"config enabled={bool(rl and rl.enabled)} rpm={getattr(rl, 'rpm', None) or ('40 (NIM default)' if nim else 'unlimited')}"
        if stats:
            detail += " | active: " + "; ".join(
                f"{v['provider']} rpm={v['rpm']} in_window={v['in_window']}" for v in stats.values())
        return ("rate limiter", True, detail, "")
    except Exception as e:
        return ("rate limiter", False, f"rate limiter broken: {e}", "")


ALL_CHECKS: List[Callable[[], Check]] = [
    _check_python, _check_deps, _check_provider, _check_registry_files,
    _check_journal, _check_skills, _check_mcp, _check_git,
    _check_fs_writable, _check_connectors, _check_rate_limit,
]


def run_doctor() -> List[Check]:
    results: List[Check] = []
    for fn in ALL_CHECKS:
        try:
            results.append(fn())
        except Exception as e:
            results.append((fn.__name__, False, f"check crashed: {e}", ""))
    return results


def format_doctor(results: List[Check]) -> str:
    lines = ["SHS Code Doctor", "=" * 60]
    failed = 0
    for name, ok, detail, hint in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        lines.append(f"[{mark}] {name}: {detail}")
        if hint:
            lines.append(f"       -> {hint}")
    lines.append("=" * 60)
    if failed:
        lines.append(f"{failed} problem(s) found. Follow the -> hints above.")
    else:
        lines.append("All systems healthy. SHS Code is ready.")
    return "\n".join(lines)
