from __future__ import annotations

"""
SHS Code — Environment Intelligence (spec §29)
================================================
Detects the actual development environment: OS, shell, runtimes, package
managers, build tools, VCS, device bridges. Never assumes a tool exists —
every command the agent runs can be validated against this first.

Detection is lazy + cached in-process (version lookups hit subprocesses
once per process lifetime, ≤ ~1s each with timeout).
"""

import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger

_TOOLS = [
    # (binary, category, --version arg)
    ("git", "vcs"), ("python3", "runtime"), ("python", "runtime"),
    ("pip", "package-manager"), ("pip3", "package-manager"),
    ("uv", "package-manager"), ("poetry", "package-manager"),
    ("node", "runtime"), ("npm", "package-manager"), ("pnpm", "package-manager"),
    ("yarn", "package-manager"), ("bun", "runtime"),
    ("deno", "runtime"),
    ("java", "runtime"), ("javac", "build"), ("kotlin", "runtime"),
    ("kotlinc", "build"), ("gradle", "build"),
    ("php", "runtime"), ("composer", "package-manager"),
    ("rustc", "runtime"), ("cargo", "build"),
    ("go", "runtime"),
    ("dotnet", "runtime"),
    ("docker", "container"), ("docker-compose", "container"),
    ("podman", "container"),
    ("adb", "mobile"), ("sdkmanager", "mobile"),
    ("flutter", "mobile"), ("xcodebuild", "mobile"),
    ("terraform", "infra"), ("ansible", "infra"),
    ("make", "build"), ("cmake", "build"), ("gcc", "build"), ("g++", "build"),
    ("clang", "build"),
    ("rg", "search"), ("fd", "search"),
    ("curl", "network"), ("wget", "network"), ("ssh", "network"),
    ("sqlite3", "database"), ("redis-cli", "database"), ("psql", "database"),
    ("ffmpeg", "media"),
]

_lock = threading.Lock()
_cache: Dict[str, Dict[str, Any]] = {}


def _which(binname: str) -> Optional[str]:
    return shutil.which(binname)


def _version(binname: str, path: str) -> str:
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True,
                           timeout=10)
        out = (r.stdout or r.stderr or "").strip().split("\n")[0]
        return out[:120]
    except Exception:
        return ""


def detect_environment(force: bool = False) -> Dict[str, Any]:
    """Full environment snapshot (cached in-process)."""
    with _lock:
        if _cache and not force:
            return _cache.get("env")  # type: ignore[return-value]

    env: Dict[str, Any] = {
        "os": platform.system(),
        "os_version": platform.release(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_exec": _which("python3") or _which("python") or "",
        "shell": os.getenv("SHELL", "") or os.getenv("COMSPEC", ""),
        "user": os.getenv("USER") or os.getenv("USERNAME", ""),
        "term": os.getenv("TERM", ""),
        "cwd": os.getcwd(),
        "tools": {},
    }

    tools: Dict[str, Dict[str, Any]] = {}
    for binname, category in _TOOLS:
        path = _which(binname)
        if path:
            tools[binname] = {"path": path, "category": category,
                              "version": _version(binname, path)}
    env["tools"] = tools
    env["tool_count"] = len(tools)

    # Android SDK heuristics
    sdk = os.getenv("ANDROID_HOME") or os.getenv("ANDROID_SDK_ROOT") or ""
    env["android_sdk"] = sdk
    if sdk and Path(sdk).exists():
        env["tools"]["adb"] = env["tools"].get("adb") or {
            "path": str(Path(sdk) / "platform-tools" / "adb"),
            "category": "mobile", "version": ""}

    with _lock:
        _cache["env"] = env
    return env


def has_tool(binname: str) -> bool:
    return binname in detect_environment()["tools"]


def tool_path(binname: str) -> Optional[str]:
    t = detect_environment()["tools"].get(binname)
    return t["path"] if t else None


def command_available(cmd: str) -> bool:
    """Check if the first token of a command exists (before executing it)."""
    first = cmd.strip().split()[0] if cmd.strip() else ""
    if not first:
        return False
    if "/" in first or "\\" in first:
        return Path(first).exists()
    return has_tool(first)


def environment_summary() -> str:
    """Compact summary for /env and context injection."""
    e = detect_environment()
    lines = [
        f"OS: {e['os']} {e['os_version']} ({e['machine']})",
        f"Python: {e['python']}  Shell: {Path(e['shell']).name if e['shell'] else '-'}",
    ]
    by_cat: Dict[str, List[str]] = {}
    for name, t in sorted(e["tools"].items()):
        by_cat.setdefault(t["category"], []).append(name)
    for cat in sorted(by_cat):
        lines.append(f"{cat}: {', '.join(by_cat[cat][:10])}")
    if e.get("android_sdk"):
        lines.append(f"Android SDK: {e['android_sdk']}")
    return "\n".join(lines)
