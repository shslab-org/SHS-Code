"""v4.4.0 SHS-Agent identity migration tests.

The dedicated GitHub identity for work performed by SHS Code moved from
the old organization profile (SHS-Code-Agent) to the dedicated personal
USER account:

    https://github.com/SHS-Agent   (id 337454460, type: User)

Why a USER account matters: GitHub's Contributors aggregation counts
user (and bot) accounts only — organizations are excluded. With the old
org identity, commits linked to the profile but never appeared in a
repository's Contributors section. The new account fixes that at the
platform level, so the runtime pins:

1. The new identity constants (login, account id, noreply email in the
   GitHub-reserved ``<id>+<login>@users.noreply.github.com`` form).
2. ZERO traces of the old identity in any ACTIVE code path (app/,
   pyproject.toml, shipped gui.html) — a repository-wide scanner.
3. The git shim enforces the NEW identity mechanically.
4. Real git commits created through SHS Code runtime paths carry the
   new author/committer (GitHub resolves them to SHS-Agent).
5. The system prompt + GUI + CLI help all reference the new identity.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

NEW_LOGIN = "SHS-Agent"
NEW_PROFILE = "https://github.com/SHS-Agent"
NEW_ACCOUNT_ID = "337454460"
NEW_EMAIL = "337454460+SHS-Agent@users.noreply.github.com"
NEW_NAME = "SHS-Agent"

OLD_LOGIN = "SHS-Code-Agent"
OLD_EMAIL_LOGIN_FORM = "SHS-Code-Agent@users.noreply.github.com"

# File globs that constitute ACTIVE code paths (shipped/runtime-relevant).
ACTIVE_GLOBS = ("app/**/*.py", "app/**/*.html", "app/**/*.js", "app/**/*.toml",
                "migrations/**/*.py", "pyproject.toml", "config.toml",
                "example*.toml")
# Documentation describing CURRENT behavior (history files excluded).
CURRENT_DOC_GLOBS = ("docs/GUI_GUIDE.md", "README.md")


class TestNewIdentityConstants:
    def test_login_and_profile(self):
        from app.git_providers import agent_identity as ai
        assert ai.AGENT_LOGIN == NEW_LOGIN
        assert ai.AGENT_PROFILE_URL == NEW_PROFILE
        assert ai.AGENT_NAME == NEW_NAME

    def test_noreply_email_is_id_prefixed_reserved_form(self):
        from app.git_providers import agent_identity as ai
        # GitHub reserves <id>+<login>@users.noreply.github.com for the
        # account with that numeric id — unspoofable, privacy-preserving.
        assert ai.AGENT_EMAIL == NEW_EMAIL
        assert ai.AGENT_EMAIL.startswith(NEW_ACCOUNT_ID + "+")
        assert ai.AGENT_EMAIL.endswith("@users.noreply.github.com")
        assert ai.AGENT_ACCOUNT_ID == NEW_ACCOUNT_ID

    def test_identity_dataclass(self):
        from app.git_providers import agent_identity as ai
        ident = ai.DEFAULT_IDENTITY
        assert ident.login == NEW_LOGIN
        assert ident.email == NEW_EMAIL
        assert ident.account_id == NEW_ACCOUNT_ID
        d = ident.as_dict()
        assert d["profile_url"] == NEW_PROFILE
        assert d["co_author_trailer"] == f"Co-Authored-By: {NEW_NAME} <{NEW_EMAIL}>"

    def test_agent_git_env_uses_new_identity(self):
        from app.git_providers import agent_identity as ai
        env = ai.agent_git_env()
        assert env["GIT_AUTHOR_NAME"] == NEW_NAME
        assert env["GIT_AUTHOR_EMAIL"] == NEW_EMAIL
        assert env["GIT_COMMITTER_NAME"] == NEW_NAME
        assert env["GIT_COMMITTER_EMAIL"] == NEW_EMAIL

    def test_agent_git_args_use_new_identity(self):
        from app.git_providers import agent_identity as ai
        args = ai.agent_git_args()
        assert f"user.name={NEW_NAME}" in args
        assert f"user.email={NEW_EMAIL}" in args


class TestOldIdentityPurged:
    def _collect_files(self, globs):
        files = []
        for g in globs:
            files.extend(REPO_ROOT.glob(g))
        return sorted(set(files))

    def test_no_old_identity_in_active_code(self):
        """The old org identity must not remain in ANY active code path."""
        offenders = []
        for f in self._collect_files(ACTIVE_GLOBS):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if OLD_LOGIN in text or OLD_EMAIL_LOGIN_FORM in text:
                offenders.append(str(f.relative_to(REPO_ROOT)))
        assert not offenders, (
            f"obsolete {OLD_LOGIN} identity still referenced in active "
            f"code paths: {offenders}")

    def test_no_old_identity_in_current_docs(self):
        offenders = []
        for f in self._collect_files(CURRENT_DOC_GLOBS):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if OLD_LOGIN in text or OLD_EMAIL_LOGIN_FORM in text:
                offenders.append(str(f.relative_to(REPO_ROOT)))
        assert not offenders, (
            f"obsolete {OLD_LOGIN} identity still referenced in current "
            f"docs: {offenders}")

    def test_shim_source_has_new_identity_only(self):
        from app.git_providers.git_shim import SHIM_SOURCE
        assert f'AGENT_NAME = "{NEW_NAME}"' in SHIM_SOURCE
        assert f'AGENT_EMAIL = "{NEW_EMAIL}"' in SHIM_SOURCE
        assert OLD_LOGIN not in SHIM_SOURCE

    def test_system_prompt_references_new_identity(self):
        from app.agent.shscode import SHS_SYSTEM_PROMPT
        assert NEW_LOGIN in SHS_SYSTEM_PROMPT
        assert "https://github.com/SHS-Agent" in SHS_SYSTEM_PROMPT
        assert OLD_LOGIN not in SHS_SYSTEM_PROMPT

    def test_gui_references_new_identity(self):
        gui = (REPO_ROOT / "app" / "server" / "static" / "gui.html")
        text = gui.read_text(encoding="utf-8")
        assert NEW_LOGIN in text
        assert NEW_EMAIL in text
        assert OLD_LOGIN not in text


class TestShimEnforcesNewIdentity:
    @pytest.fixture(autouse=True)
    def _shim_env(self):
        from app.git_providers.agent_identity import apply_agent_git_env
        apply_agent_git_env()
        yield

    def _repo(self, tmp_path):
        def run(*args, **kw):
            return subprocess.run(["git"] + list(args), cwd=tmp_path,
                                  capture_output=True, text=True, **kw)
        run("init", "-q")
        run("config", "user.name", "Human User")
        run("config", "user.email", "human@example.com")
        (tmp_path / "seed.txt").write_text("seed\n")
        run("add", "-A")
        run("commit", "-q", "-m", "seed")
        return run

    def _last_identity(self, run):
        r = run("log", "-1", "--pretty=format:%an|%ae|%cn|%ce")
        return r.stdout.strip()

    def test_installed_shim_carries_new_identity(self):
        from app.git_providers.git_shim import shim_path, shim_active_on_path
        assert shim_path().exists()
        assert shim_active_on_path()
        text = shim_path().read_text(encoding="utf-8")
        assert f'AGENT_EMAIL = "{NEW_EMAIL}"' in text
        assert OLD_LOGIN not in text

    def test_commit_via_shim_attributed_to_new_identity(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "new.txt").write_text("v440\n")
        run("add", "-A")
        run("commit", "-q", "-m", "v4.4.0 identity")
        ident = self._last_identity(run)
        # author name, author email, committer name, committer email
        assert ident.count(NEW_LOGIN) == 4
        assert ident.count(NEW_EMAIL) == 2
        assert "human@example.com" not in ident

    def test_author_bypass_still_defeated_with_new_identity(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "x.txt").write_text("x\n")
        run("add", "-A")
        run("commit", "-q", "-m", "bypass attempt",
            "--author=Impostor <impostor@evil.com>")
        ident = self._last_identity(run)
        assert ident.startswith(f"{NEW_LOGIN}|")
        assert "impostor" not in ident.lower()

    def test_provider_commit_attributed_to_new_identity(self, tmp_path):
        from app.git_providers.github_provider import GitHubProvider
        self._repo(tmp_path)
        (tmp_path / "p.txt").write_text("p\n")
        gh = GitHubProvider(repo_dir=str(tmp_path))
        out = gh.commit("provider v4.4.0")
        assert out["author"] == f"{NEW_NAME} <{NEW_EMAIL}>"
        r = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%an|%ae|%cn|%ce"],
            cwd=tmp_path, capture_output=True, text=True)
        assert r.stdout.count(NEW_EMAIL) == 2
        assert f"Co-Authored-By: {NEW_NAME} <{NEW_EMAIL}>" in out["message"]
