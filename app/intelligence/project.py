from __future__ import annotations

"""
SHS Code — Project Detection (spec §2, §28)
============================================
Detects project type, languages, frameworks, entry points, dependency
files, build/test/run commands, important files — from the actual
filesystem (never from documentation claims).

Result is a ProjectProfile dict persisted by the manager layer
(~/.manusclaw/intel/<hash>/profile.json) so /project can show it and
the verification engine can pick project-aware commands.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger

# ── project type signatures ──────────────────────────────────────────────────

_TYPE_SIGNATURES = [
    # (type, detector-file, extra test)
    ("python", "pyproject.toml", None),
    ("python", "setup.py", None),
    ("python", "setup.cfg", None),
    ("node", "package.json", None),
    ("android-gradle", "build.gradle", None),
    ("android-gradle", "build.gradle.kts", None),
    ("gradle", "build.gradle", None),
    ("gradle", "build.gradle.kts", None),
    ("php", "composer.json", None),
    ("rust", "Cargo.toml", None),
    ("go", "go.mod", None),
    ("dotnet", "*.csproj", None),
    ("swift", "Package.swift", None),
    ("docker", "Dockerfile", None),
]

_FRAMEWORK_HINTS = {
    # file -> framework
    "package.json": "node",
    "next.config.js": "Next.js", "next.config.mjs": "Next.js", "next.config.ts": "Next.js",
    "vite.config.js": "Vite", "vite.config.ts": "Vite",
    "react": "React",
    "angular.json": "Angular",
    "vue.config.js": "Vue",
    "tailwind.config.js": "Tailwind", "tailwind.config.ts": "Tailwind",
    "express": "Express", "fastify": "Fastify", "nest": "NestJS",
    "nuxt.config.js": "Nuxt", "nuxt.config.ts": "Nuxt",
    "svelte.config.js": "Svelte",
    "requirements.txt": "python-deps", "Pipfile": "pipenv",
    "poetry.lock": "poetry", "uv.lock": "uv",
    "Gemfile": "ruby-bundler", "pom.xml": "maven",
    "deno.json": "Deno", "bun.lockb": "Bun",
}

_ENTRY_CANDIDATES = [
    "main.py", "app.py", "run.py", "manage.py", "cli.py", "server.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "app.js",
    "src/main.py", "src/app.py", "src/main.js", "src/main.ts", "src/index.ts",
    "src/main/java", "src/main/kotlin", "app/src/main/java",
    "MainActivity.kt", "MainActivity.java", "cmd/main.go",
    "index.php", "public/index.php",
]

IMPORTANT_FILES = [
    "README.md", "README", "CHANGELOG.md", "LICENSE", "CONTRIBUTING.md",
    "pyproject.toml", "setup.py", "requirements.txt", "package.json",
    "tsconfig.json", "build.gradle", "build.gradle.kts", "settings.gradle",
    "composer.json", "Cargo.toml", "go.mod", "Dockerfile",
    "docker-compose.yml", ".env.example", "config.toml", "Makefile",
    ".github/workflows", "docs", "SHS_CODE_IMPLEMENTATION_STATE.md",
]


def _has(root: Path, name: str) -> bool:
    return (root / name).exists()


def _read_json(root: Path, name: str) -> Optional[dict]:
    try:
        return json.loads((root / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def detect_project_type(root: Path) -> Dict[str, Any]:
    ptype = "unknown"
    detected_via = ""
    for t, sig, _ in _TYPE_SIGNATURES:
        if sig.startswith("*"):
            if any(root.glob(sig)):
                ptype, detected_via = t, sig
                break
        elif _has(root, sig):
            ptype, detected_via = t, sig
            break
    # gradle vs android: look for android manifest / gradle wrapper dir
    if ptype in ("android-gradle", "gradle"):
        if (root / "app" / "src" / "main").exists() or any(
                root.glob("app/src/main/AndroidManifest.xml")):
            ptype = "android-gradle"
        elif any(root.glob("src/main/AndroidManifest.xml")):
            ptype = "android-gradle"
        else:
            ptype = "gradle"
    # python fallback: many .py files without packaging
    if ptype == "unknown":
        pys = list(root.glob("*.py"))[:3]
        if pys:
            ptype, detected_via = "python", "(.py files present)"
    return {"type": ptype, "detected_via": detected_via}


def detect_frameworks(root: Path) -> List[str]:
    frameworks: List[str] = []
    pkg = _read_json(root, "package.json")
    if pkg:
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        for dep, fw in (("react", "React"), ("vue", "Vue"), ("next", "Next.js"),
                        ("express", "Express"), ("fastify", "Fastify"),
                        ("@nestjs/core", "NestJS"), ("svelte", "Svelte"),
                        ("@angular/core", "Angular"), ("tailwindcss", "Tailwind"),
                        ("vite", "Vite"), ("electron", "Electron"),
                        ("discord.js", "discord.js"), ("telegram", "Telegram bot"),
                        ("prisma", "Prisma"), ("typeorm", "TypeORM"),
                        ("jest", "Jest"), ("vitest", "Vitest"), ("mocha", "Mocha"),
                        ("typescript", "TypeScript")):
            if dep in deps:
                frameworks.append(fw)
    pyproj = (root / "pyproject.toml").read_text(encoding="utf-8", errors="ignore") \
        if _has(root, "pyproject.toml") else ""
    req = (root / "requirements.txt").read_text(encoding="utf-8", errors="ignore") \
        if _has(root, "requirements.txt") else ""
    pytext = pyproj + "\n" + req
    for dep, fw in (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"),
                    ("torch", "PyTorch"), ("tensorflow", "TensorFlow"),
                    ("sqlalchemy", "SQLAlchemy"), ("pydantic", "Pydantic"),
                    ("pytest", "pytest"), ("aiohttp", "aiohttp"),
                    ("rich", "rich"), ("langchain", "LangChain")):
        if dep in pytext.lower():
            frameworks.append(fw)
    for f in ("next.config.js", "next.config.mjs", "next.config.ts"):
        if _has(root, f):
            frameworks.append("Next.js")
    if _has(root, "vite.config.js") or _has(root, "vite.config.ts"):
        frameworks.append("Vite")
    if _has(root, "tailwind.config.js") or _has(root, "tailwind.config.ts"):
        frameworks.append("Tailwind")
    if _has(root, "settings.gradle") or _has(root, "settings.gradle.kts"):
        frameworks.append("Gradle multi-module")
    # Android specifics
    if any(root.glob("app/src/main/**/AndroidManifest.xml")) or (
            _has(root, "app") and (root / "app" / "build.gradle").exists()):
        frameworks.append("Android app")
    for f in ("compose", ):
        if any(root.glob("app/build.gradle*")):
            g = ""
            for bf in ("app/build.gradle", "app/build.gradle.kts"):
                if _has(root, bf):
                    g = (root / bf).read_text(encoding="utf-8", errors="ignore").lower()
                    break
            if "compose" in g:
                frameworks.append("Jetpack Compose")
            if "kotlin" in g:
                frameworks.append("Kotlin Android")
    return list(dict.fromkeys(frameworks))


def detect_entry_points(root: Path) -> List[str]:
    entries: List[str] = []
    for cand in _ENTRY_CANDIDATES:
        p = root / cand
        if p.is_file():
            entries.append(cand)
        elif p.is_dir():
            entries.append(cand + "/")
    # console scripts in pyproject
    py = _read_json(root, "pyproject.toml")
    # python -m style: src layout main modules
    for mod_dir in ("src", "app", "cli", "server"):
        d = root / mod_dir
        if d.is_dir() and (d / "__init__.py").exists() and (d / "__main__.py").exists():
            entries.append(f"{mod_dir}/__main__.py")
    # package.json bin / main
    pkg = _read_json(root, "package.json")
    if pkg:
        if pkg.get("bin"):
            entries.append("package.json bin: " + ", ".join(list(pkg["bin"])[:3]))
        if pkg.get("main"):
            entries.append(f"main: {pkg['main']}")
        if any("dev" in k and "script" for k in (pkg.get("scripts") or {})):
            pass
    return entries[:12]


def detect_commands(root: Path, ptype: str) -> Dict[str, List[str]]:
    """Project-aware build/test/run/lint commands (spec §15)."""
    pkg = _read_json(root, "package.json")
    scripts = (pkg or {}).get("scripts") or {}
    c: Dict[str, List[str]] = {}

    if ptype == "python":
        c["build"] = ["python -m compileall -q .", "python -m build"]
        c["test"] = ["python -m pytest -x -q"]
        c["lint"] = ["python -m ruff check ."]
        c["run"] = ["python main.py", "python -m app.cli"]
    elif ptype == "node":
        pm = "npm"
        if _has(root, "pnpm-lock.yaml"):
            pm = "pnpm"
        elif _has(root, "yarn.lock"):
            pm = "yarn"
        elif _has(root, "bun.lockb"):
            pm = "bun"
        c["validate"] = [f"{pm} install --package-lock-only"]
        if _has(root, "tsconfig.json"):
            c["typecheck"] = [f"{pm} run typecheck" if "typecheck" in scripts
                              else f"{pm} exec tsc --noEmit"]
        c["test"] = [f"{pm} test"] if "test" in scripts else []
        b = f"{pm} run build" if "build" in scripts else f"{pm} run bundle"
        c["build"] = [b]
        dev = f"{pm} run dev" if "dev" in scripts else f"{pm} start"
        c["run"] = [dev]
    elif ptype == "android-gradle":
        c["build"] = ["./gradlew assembleDebug"]
        c["test"] = ["./gradlew test"]
        c["lint"] = ["./gradlew lint"]
        c["run"] = ["./gradlew installDebug"]
    elif ptype == "gradle":
        c["build"] = ["./gradlew build"]
        c["test"] = ["./gradlew test"]
    elif ptype == "php":
        c["validate"] = ["php -l", "composer validate"]
        c["test"] = ["vendor/bin/phpunit"] if _has(root, "phpunit.xml") else []
        c["run"] = ["php -S localhost:8000"]
    elif ptype == "rust":
        c["build"] = ["cargo build"]
        c["test"] = ["cargo test"]
        c["lint"] = ["cargo clippy"]
        c["run"] = ["cargo run"]
    elif ptype == "go":
        c["build"] = ["go build ./..."]
        c["test"] = ["go test ./..."]
        c["vet"] = ["go vet ./..."]
    return {k: v for k, v in c.items() if v}


def detect_dependency_files(root: Path) -> List[str]:
    names = ["requirements.txt", "pyproject.toml", "Pipfile", "poetry.lock",
             "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
             "composer.json", "composer.lock", "Cargo.toml", "Cargo.lock",
             "go.mod", "go.sum", "Gemfile", "Gemfile.lock", "pom.xml"]
    return [n for n in names if _has(root, n)]


def detect_test_frameworks(root: Path) -> List[str]:
    found: List[str] = []
    if _has(root, "pytest.ini") or (root / "tests").is_dir() or _has(root, "pyproject.toml"):
        found.append("pytest (python)")
    pkg = _read_json(root, "package.json")
    if pkg:
        dev = {**(pkg.get("devDependencies") or {})}
        for d, fw in (("jest", "Jest"), ("vitest", "Vitest"), ("mocha", "Mocha"),
                      ("@playwright/test", "Playwright"), ("cypress", "Cypress")):
            if d in dev:
                found.append(f"{fw} (node)")
    if _has(root, "phpunit.xml"):
        found.append("PHPUnit (php)")
    if _has(root, "Cargo.toml"):
        found.append("cargo test (rust)")
    if _has(root, "go.mod"):
        found.append("go test (go)")
    return found


def git_state(root: Path) -> Dict[str, Any]:
    """Fast git snapshot (branch, dirty count, last commit). Non-fatal."""
    def _git(*args: str) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                               text=True, timeout=8)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return {"is_repo": False}
    status = _git("status", "--porcelain")
    dirty = [l for l in status.split("\n") if l.strip()]
    staged = [l for l in dirty if l.startswith(("A ", "M ", "D ", "R "))] if status else []
    last = _git("log", "-1", "--pretty=format:%h %s")
    remote = _git("remote", "get-url", "origin")
    return {
        "is_repo": True,
        "branch": branch,
        "dirty_files": len(dirty),
        "staged_files": len(staged),
        "dirty_sample": [l[3:] for l in dirty[:8]],
        "last_commit": last[:120],
        "remote": remote,
    }


def build_profile(root: Path, language_stats: Optional[Dict[str, int]] = None,
                  file_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    type_info = detect_project_type(root)
    profile: Dict[str, Any] = {
        "root": str(root),
        "name": root.name,
        **type_info,
        "frameworks": detect_frameworks(root),
        "entry_points": detect_entry_points(root),
        "dependency_files": detect_dependency_files(root),
        "test_frameworks": detect_test_frameworks(root),
        "commands": detect_commands(root, type_info["type"]),
        "important_files": [f for f in IMPORTANT_FILES if _has(root, f)],
        "languages": language_stats or {},
        "file_stats": file_stats or {},
        "git": git_state(root),
    }
    return profile


def summarize_profile(profile: Dict[str, Any]) -> str:
    """Compact human/LLM-readable project summary (for context injection)."""
    lines = [
        f"PROJECT: {profile.get('name')}  ({profile.get('type')} via {profile.get('detected_via')})",
    ]
    if profile.get("frameworks"):
        lines.append(f"Frameworks: {', '.join(profile['frameworks'][:8])}")
    if profile.get("languages"):
        top = sorted(profile["languages"].items(), key=lambda kv: -kv[1])[:6]
        lines.append("Languages: " + ", ".join(f"{k} ({v} files)" for k, v in top))
    fs = profile.get("file_stats") or {}
    if fs:
        lines.append(f"Indexed: {fs.get('files', 0)} files, {fs.get('lines', 0)} lines")
    if profile.get("entry_points"):
        lines.append("Entry points: " + ", ".join(profile["entry_points"][:6]))
    if profile.get("test_frameworks"):
        lines.append("Tests: " + ", ".join(profile["test_frameworks"][:5]))
    cmds = profile.get("commands") or {}
    if cmds:
        for k in ("build", "test", "run"):
            if cmds.get(k):
                lines.append(f"{k}: {cmds[k][0]}")
    g = profile.get("git") or {}
    if g.get("is_repo"):
        lines.append(f"Git: branch={g['branch']}, dirty={g['dirty_files']}, last={g.get('last_commit', '')[:60]}")
    return "\n".join(lines)
