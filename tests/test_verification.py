"""SHS Code Phase 2 — Verification Engine + Recovery tests (spec §15-§17, §44-§45)."""
import asyncio

import pytest

from app.verification import VerificationEngine, format_verification
from app.recovery import (
    diagnose, classify_error, retry_strategy, extract_retry_after,
    should_change_strategy, ErrorClass, RetryStrategy,
)


@pytest.fixture
def py_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "vtest"\n')
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text(
        "from pkg.core import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    return tmp_path


class TestCommandSelection:
    def test_python_selects_build_and_test(self, py_project):
        ve = VerificationEngine(py_project)
        kinds = ve.select_kinds("python")
        assert "build" in kinds and "test" in kinds
        assert "typecheck" not in kinds

    def test_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"scripts": {"test": "jest", "build": "vite"},'
            ' "devDependencies": {"typescript": "1"}}')
        (tmp_path / "tsconfig.json").write_text("{}")
        ve = VerificationEngine(tmp_path)
        kinds = ve.select_kinds("node", level="thorough")
        assert {"typecheck", "build", "test"} <= set(kinds)
        (tmp_path / "package-lock.json").write_text("{}")
        kinds2 = ve.select_kinds("node", level="thorough")
        assert "validate" in kinds2

    def test_unknown_type_no_commands(self, tmp_path):
        ve = VerificationEngine(tmp_path)
        assert ve.select_kinds("unknown") == []

    def test_level_fast_skips_tests(self, py_project):
        ve = VerificationEngine(py_project)
        assert ve.select_kinds("python", level="fast") == ["build"]


class TestVerificationExecution:
    def test_passing_project(self, py_project):
        ve = VerificationEngine(py_project)
        report = asyncio.run(ve.verify(level="fast"))
        assert report["project_type"] == "python"
        assert report["ok"] is True
        labels = [r["label"] for r in report["results"]]
        assert any("py-compile" in l for l in labels)

    def test_failing_project_detected(self, py_project):
        (py_project / "pkg" / "broken.py").write_text("def broken(:\n    pass\n")
        ve = VerificationEngine(py_project)
        report = asyncio.run(ve.verify(kinds=["build"]))
        assert report["ok"] is False
        analysis = ve.analyze_failure(report)
        assert analysis["ok"] is False
        assert analysis["hypotheses"], "no hypotheses extracted"
        assert analysis["suggested_actions"]

    def test_syntax_kind_targets_changed_files(self, py_project):
        (py_project / "pkg" / "new.py").write_text("x = 1\n")
        ve = VerificationEngine(py_project)
        cmds = ve._commands_for("syntax", "python", ["pkg/new.py"])
        assert any("new.py" in c[1] for c in cmds)

    def test_error_extraction_patterns(self):
        out = (
            "E   AssertionError: expected 3 got 4\n"
            "FAILED tests/test_x.py::test_add - assert 3 == 4\n"
            "ModuleNotFoundError: No module named 'flask'\n"
            "error TS2322: Type 'string' is not assignable to 'number'\n"
            "FAILURE: Build failed with an exception.\n"
            "Execution failed for task ':app:compileDebugKotlin'.\n")
        errs = VerificationEngine.extract_errors(out)
        classes = {e["class"] for e in errs}
        assert "test-failure" in classes
        assert "python-import" in classes
        assert "ts-error" in classes
        assert "gradle-failure" in classes

    def test_format_verification(self, py_project):
        ve = VerificationEngine(py_project)
        report = asyncio.run(ve.verify(level="fast"))
        s = format_verification(report)
        assert "VERIFICATION" in s
        assert "PASS" in s or "✓" in s


class TestErrorClassification:
    def test_rate_limit(self):
        d = diagnose("HTTP 429 Too Many Requests, retry-after: 37")
        assert d.error_class == ErrorClass.RATE_LIMIT
        assert d.strategy == RetryStrategy.WAIT_AND_RETRY
        assert d.wait_s == 37.0

    def test_missing_api_key_needs_user(self):
        d = diagnose("Invalid API key provided for provider", context="llm")
        assert d.strategy in (RetryStrategy.REQUIRES_USER, RetryStrategy.REQUIRES_FIX)
        d2 = diagnose("missing api key: no credentials configured")
        assert d2.strategy == RetryStrategy.REQUIRES_USER

    def test_code_error_requires_fix(self):
        assert diagnose("SyntaxError: invalid syntax").strategy == \
            RetryStrategy.REQUIRES_FIX
        assert diagnose("ModuleNotFoundError: no flask").strategy == \
            RetryStrategy.REQUIRES_FIX

    def test_network_retryable(self):
        assert diagnose("Connection reset by peer").strategy == \
            RetryStrategy.RETRYABLE

    def test_environment_blocker(self):
        assert diagnose("gradle: command not found").strategy == \
            RetryStrategy.EXTERNAL_BLOCKER

    def test_conflict_and_git(self):
        assert diagnose("<<<<<<< HEAD merge conflict").error_class == ErrorClass.GIT

    def test_extract_retry_after(self):
        assert extract_retry_after("Retry-After: 12") == 12.0
        assert extract_retry_after("no header here") is None

    def test_strategy_change_after_repeats(self):
        # spec §17: repeated identical failures force strategy change
        assert should_change_strategy(3, 3, RetryStrategy.RETRYABLE) is True
        assert should_change_strategy(1, 1, RetryStrategy.RETRYABLE) is False
        assert should_change_strategy(5, 5, RetryStrategy.REQUIRES_USER) is False

    def test_diagnosis_render(self):
        r = diagnose("429 rate limit")
        assert "RATE_LIMIT_ERROR" in r.render()
        assert "WAIT_AND_RETRY" in r.render()
