"""Entry-point regression tests (FIX SPEC §1 + §2, v4.0.0 patch, no version bump).

§1: run_flow.py --help must display help and exit 0 without starting
    an agent task, requiring idle agent, or invoking the LLM.
§2: python -m app and python -m app.server must work (intended module
    paths); python -m shscode is architecturally invalid (distribution
    name is shscode but import package is app/ — pyproject
    [tool.setuptools.packages.find] includes only app*).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestRunFlowHelp:
    def test_help_exits_zero_with_usage(self):
        p = _run("run_flow.py", "--help")
        assert p.returncode == 0, p.stderr
        out = p.stdout + p.stderr
        assert "usage" in out.lower()
        assert "PlanningFlow" in out or "goal" in out.lower()

    def test_short_help_exits_zero(self):
        p = _run("run_flow.py", "-h")
        assert p.returncode == 0, p.stderr
        assert "usage" in (p.stdout + p.stderr).lower()

    def test_help_does_not_start_agent(self):
        p = _run("run_flow.py", "--help")
        out = (p.stdout + p.stderr).lower()
        assert "agent-not-idle" not in out
        assert "agent not idle" not in out
        assert "flow result" not in out


class TestModuleExecution:
    def test_python_m_app_help(self):
        p = _run("-m", "app", "--help")
        assert p.returncode == 0, p.stderr
        assert "usage" in (p.stdout + p.stderr).lower()

    def test_python_m_app_cli_help(self):
        p = _run("-m", "app.cli", "--help")
        assert p.returncode == 0, p.stderr
        assert "usage" in (p.stdout + p.stderr).lower()

    def test_python_m_app_server_help(self):
        p = _run("-m", "app.server", "--help")
        assert p.returncode == 0, p.stderr
        out = (p.stdout + p.stderr).lower()
        assert "usage" in out
        assert "agent server" in out or "host" in out

    def test_python_m_shscode_invalid_proven(self):
        """Prove python -m shscode is architecturally invalid: no top-level
        shscode import package exists (import package is app/)."""
        assert not (REPO_ROOT / "shscode.py").exists()
        assert not (REPO_ROOT / "shscode").is_dir()
        p = _run("-m", "shscode")
        assert p.returncode != 0
        assert "no module named shscode" in (p.stdout + p.stderr).lower()
