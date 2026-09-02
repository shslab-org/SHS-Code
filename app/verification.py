from __future__ import annotations

"""
SHS Code — Verification Engine (spec §15)
==========================================
Dedicated project-aware verification layer:

  IMPLEMENT → BUILD → TEST → LINT → RUN → INSPECT → VERIFY

Selects ONLY the checks appropriate for the detected project (never blindly
runs everything — spec §15 "select appropriate verification"):
  python        : compileall (import/syntax validation) + pytest
  node          : package validation + typecheck + tests
  android-gradle: compileDebugKotlin (fast) + gradle test
  gradle        : build + test
  php           : php -l on changed files + composer validate
  rust          : cargo build + test
  go            : go build + go vet
  unknown       : no-op with explicit "no verification commands known"

Each command runs bounded (timeout), output is captured + tail-limited,
exit codes classify success, and the result is journaled
(record_verification + record_test_result) so /status can show it.

Used by: the agent `verify` tool, /doctor, /status, and the post-work
verification hook in the agent loop.
"""

import asyncio
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.logger import logger

MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT = 420   # 7 min per command


class VerificationEngine:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()

    # ------------------------------------------------------------------
    # Command selection (project-aware)
    # ------------------------------------------------------------------

    def _commands_for(self, kind: str, ptype: str,
                      changed_files: List[str]) -> List[Tuple[str, str]]:
        """(label, command) pairs for a verification kind, by project type."""
        has = lambda f: (self.root / f).exists()  # noqa: E731
        cmds: List[Tuple[str, str]] = []

        if kind == "build":
            if ptype == "python":
                cmds.append(("build/py-compile", "python3 -m compileall -q ."))
            elif ptype == "node":
                if "build" in ((self._pkg_scripts() or {})):
                    cmds.append(("build/pkg", "npm run build"))
            elif ptype == "android-gradle":
                cmds.append(("build/gradle-compile",
                             "./gradlew compileDebugKotlin -q"))
            elif ptype == "gradle":
                cmds.append(("build/gradle", "./gradlew build -q"))
            elif ptype == "rust":
                cmds.append(("build/cargo", "cargo build"))
            elif ptype == "go":
                cmds.append(("build/go", "go build ./..."))
            elif ptype == "php":
                cmds.append(("build/php-lint-all", "php -l index.php"))
        elif kind == "test":
            if ptype == "python":
                if (self.root / "tests").is_dir() or has("pytest.ini"):
                    cmds.append(("test/pytest", "python3 -m pytest -x -q --no-header -p no:cacheprovider 2>&1 | tail -60"))
            elif ptype == "node":
                scripts = self._pkg_scripts() or {}
                if "test" in scripts:
                    cmds.append(("test/pkg", "npm test --silent 2>&1 | tail -60"))
            elif ptype in ("android-gradle", "gradle"):
                cmds.append(("test/gradle", "./gradlew test -q 2>&1 | tail -40"))
            elif ptype == "rust":
                cmds.append(("test/cargo", "cargo test -q"))
            elif ptype == "go":
                cmds.append(("test/go", "go test ./..."))
        elif kind == "lint":
            if ptype == "python":
                if (self.root / ".ruff.toml").exists() or has("pyproject.toml"):
                    cmds.append(("lint/ruff", "python3 -m ruff check . 2>&1 | tail -30"))
            elif ptype == "rust":
                cmds.append(("lint/clippy", "cargo clippy -q 2>&1 | tail -30"))
            elif ptype == "go":
                cmds.append(("lint/go-vet", "go vet ./..."))
        elif kind == "validate":
            if ptype == "node":
                if has("package-lock.json"):
                    cmds.append(("validate/pkg-lock", "npm install --package-lock-only --no-audit --no-fund 2>&1 | tail -20"))
            elif ptype == "php":
                if has("composer.json"):
                    cmds.append(("validate/composer", "composer validate --no-check-publish 2>&1 | tail -20"))
        elif kind == "typecheck":
            if ptype == "node" and has("tsconfig.json"):
                cmds.append(("typecheck/tsc", "npx tsc --noEmit 2>&1 | tail -40"))
        elif kind == "syntax":
            # fast targeted check for changed PHP/Python files
            targets = [f for f in changed_files if f.endswith((".php", ".py"))][:20]
            for f in targets:
                if f.endswith(".php"):
                    cmds.append((f"syntax/{f}", f"php -l {f}"))
                else:
                    cmds.append((f"syntax/{f}", f"python3 -m py_compile {f}"))
        return cmds

    def _pkg_scripts(self) -> Optional[Dict[str, str]]:
        try:
            import json
            pkg = json.loads((self.root / "package.json").read_text(encoding="utf-8"))
            return pkg.get("scripts") or {}
        except Exception:
            return None

    def select_kinds(self, ptype: str, changed_files: Optional[List[str]] = None,
                     level: str = "standard") -> List[str]:
        """Which verification kinds apply to this project (spec §15)."""
        kinds = ["build", "test"]
        if level == "fast":
            kinds = ["build"]
        if level == "thorough":
            kinds = ["validate", "typecheck", "build", "test", "lint"]
        if changed_files and ptype == "php":
            kinds = ["syntax", "build", "test"]
        return [k for k in kinds
                if any(self._commands_for(k, ptype, changed_files or []))]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _run(self, label: str, cmd: str,
                   timeout: int) -> Dict[str, Any]:
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, cwd=str(self.root),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            try:
                out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {"label": label, "cmd": cmd, "ok": False,
                        "exit_code": None, "timed_out": True,
                        "duration_s": round(time.monotonic() - t0, 1),
                        "output": f"(timed out after {timeout}s)"}
            out = (out_b or b"").decode("utf-8", errors="replace")
            return {
                "label": label, "cmd": cmd, "ok": proc.returncode == 0,
                "exit_code": proc.returncode, "timed_out": False,
                "duration_s": round(time.monotonic() - t0, 1),
                "output": out[-MAX_OUTPUT_CHARS:],
            }
        except Exception as e:
            return {"label": label, "cmd": cmd, "ok": False, "exit_code": None,
                    "timed_out": False, "error": str(e)[:300],
                    "duration_s": round(time.monotonic() - t0, 1), "output": ""}

    async def verify(self, kinds: Optional[List[str]] = None,
                     changed_files: Optional[List[str]] = None,
                     level: str = "standard",
                     timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        """Run the verification pipeline. Returns a structured report."""
        ptype = "unknown"
        profile: Dict[str, Any] = {}
        try:
            from app.intelligence import get_intelligence
            profile = get_intelligence(self.root).profile()
            ptype = profile.get("type", "unknown")
        except Exception as e:
            logger.debug(f"[Verify] profile detection failed: {e}")

        if kinds is None:
            kinds = self.select_kinds(ptype, changed_files, level)
        results: List[Dict[str, Any]] = []
        for kind in kinds:
            for label, cmd in self._commands_for(kind, ptype, changed_files or []):
                from app.activity import emit
                emit("verifying", label=label, what=kind)
                res = await self._run(label, cmd, timeout)
                res["kind"] = kind
                results.append(res)

        ok = bool(results) and all(r["ok"] for r in results)
        report = {
            "kind": "verification", "project_type": ptype, "ok": ok,
            "kinds": kinds, "results": results,
            "summary": self._summarize(results),
        }
        if profile:
            report["project"] = profile.get("name")
        return report

    @staticmethod
    def _summarize(results: List[Dict[str, Any]]) -> str:
        if not results:
            return "no verification commands known for this project type"
        parts = []
        for r in results:
            mark = "✓" if r["ok"] else "✗"
            extra = " (timeout)" if r.get("timed_out") else ""
            parts.append(f"{mark} {r['label']} [{r['duration_s']}s{extra}]")
        return "; ".join(parts)

    # ------------------------------------------------------------------
    # Failure analysis (spec §16 build recovery, §17 test recovery)
    # ------------------------------------------------------------------

    @staticmethod
    def extract_errors(output: str, max_errors: int = 12) -> List[Dict[str, str]]:
        """Pull actionable error lines out of build/test output."""
        patterns = [
            (r"^(?:\S+\.py:\d+.*\n)?\s*(SyntaxError:.+)$", "python-syntax"),
            (r"^(ModuleNotFoundError:.+)$", "python-import"),
            (r"^(ImportError:.+)$", "python-import"),
            (r"^(IndentationError:.+)$", "python-syntax"),
            (r"^E\s+\S+", "pytest-failure"),
            (r"^(FAILED|ERROR)\s+(\S+)", "test-failure"),
            (r"^(.+\.py:\d+:\s+.+?Error:.+)$", "python-runtime"),
            (r"error TS\d+:\s*(.+)$", "ts-error"),
            (r"^(.+)\((\d+),(\d+)\):\s*error\s+(.+)$", "compile-error"),
            (r"npm ERR!.*$", "npm-error"),
            (r"^error:.+$", "rustc-error"),
            (r"FAILURE:\s*Build failed with an exception\.*", "gradle-failure"),
            (r"Execution failed for task '([^']+)'.*", "gradle-task"),
            (r"PHP\s+Fatal error:\s*(.+)$", "php-fatal"),
            (r"PHP\s+Parse error:\s*(.+)$", "php-parse"),
            (r"^(.*):(\d+):\s*(error|warning):\s*(.+)$", "gcc-error"),
            (r"^#\[error\].*$", "go-error"),
        ]
        errors: List[Dict[str, str]] = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            for rx, cls in patterns:
                m = re.match(rx, line)
                if m:
                    errors.append({"class": cls, "line": line[:240]})
                    break
            if len(errors) >= max_errors:
                break
        return errors

    def analyze_failure(self, report: Dict[str, Any],
                        changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """DIAGNOSE → hypotheses → suggested fixes (spec §16).
        Feeds the agent's recovery loop with concrete next actions."""
        failed = [r for r in report.get("results", []) if not r.get("ok")]
        if not failed:
            return {"ok": True, "hypotheses": [], "suggested_actions": []}
        hypotheses: List[Dict[str, str]] = []
        for r in failed:
            errs = self.extract_errors(r.get("output", ""))
            for e in errs:
                h = {"source": r["label"], "class": e["class"], "evidence": e["line"]}
                if e["class"] in ("python-import", "python-syntax"):
                    h["hypothesis"] = "code error in changed files (import path or syntax)"
                    h["fix"] = "inspect the file at the reported line; fix import/syntax"
                elif e["class"] == "test-failure":
                    h["hypothesis"] = "regression: changed behavior broke a test"
                    h["fix"] = "run the single failing test with -x, inspect assertion"
                elif e["class"] in ("npm-error",):
                    h["hypothesis"] = "dependency problem"
                    h["fix"] = "check package.json/lockfile consistency; npm install"
                elif e["class"] in ("gradle-task", "gradle-failure"):
                    h["hypothesis"] = "build configuration or code error in module"
                    h["fix"] = "run the failing gradle task with --stacktrace"
                elif e["class"] in ("ts-error", "compile-error", "gcc-error",
                                    "rustc-error", "php-fatal", "php-parse"):
                    h["hypothesis"] = "compile-level code error"
                    h["fix"] = "fix the reported file/line; recompile"
                else:
                    h["hypothesis"] = "unclassified failure"
                    h["fix"] = "read full output; compare with last known-good"
                hypotheses.append(h)
        suggested = list(dict.fromkeys(
            h["fix"] for h in hypotheses if h.get("fix")))[:8]
        return {"ok": False, "failed": len(failed),
                "hypotheses": hypotheses[:12], "suggested_actions": suggested}


def format_verification(report: Dict[str, Any]) -> str:
    """LLM/human-readable verification report."""
    lines = [f"VERIFICATION — project: {report.get('project', '?')} "
             f"({report.get('project_type', '?')})  "
             f"{'ALL PASS ✓' if report.get('ok') else 'FAILURES ✗'}"]
    for r in report.get("results", []):
        mark = "✓" if r["ok"] else "✗"
        lines.append(f"  {mark} {r['label']}  [{r['duration_s']}s] {r['cmd'][:100]}")
        if not r["ok"]:
            tail = (r.get("output") or "").strip().split("\n")
            lines += [f"     │ {l[:160]}" for l in tail[-8:]]
    return "\n".join(lines)
