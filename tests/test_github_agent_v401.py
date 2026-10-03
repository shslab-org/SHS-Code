"""v4.0.1 SHS-Code-Agent GitHub identity tests (mission §17).

Pins:
1. The Co-Authored-By trailer format (GitHub's supported credit mechanism).
2. GitHubProvider.commit() adds the trailer to every commit message.
3. Token resolution priority (app > SHSCODE_GITHUB_TOKEN > GITHUB_TOKEN).
4. GitHub App JWT minting shape (when PyJWT available).
5. No token ever leaks into stored remote URLs after clone/push helpers.
"""
from __future__ import annotations

import os
import subprocess

import pytest


class TestAgentIdentity:
    def test_trailer_format(self):
        from app.git_providers.agent_identity import DEFAULT_IDENTITY
        t = DEFAULT_IDENTITY.co_author_trailer()
        assert t == ("Co-Authored-By: SHS-Code-Agent "
                     "<SHS-Code-Agent@users.noreply.github.com>")
        assert t.startswith("Co-Authored-By: ")

    def test_profile_url(self):
        from app.git_providers.agent_identity import AGENT_PROFILE_URL
        assert AGENT_PROFILE_URL == "https://github.com/SHS-Code-Agent"

    def test_token_priority(self, monkeypatch):
        from app.git_providers import agent_identity as ai
        # clear the installation-token cache + app env
        monkeypatch.delenv("SHSCODE_GITHUB_APP_ID", raising=False)
        monkeypatch.delenv("SHSCODE_GITHUB_APP_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("SHSCODE_GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("SHSCODE_GITHUB_APP_INSTALLATION_ID", raising=False)
        ai.get_installation_token._cache = None  # type: ignore[attr-defined]

        monkeypatch.delenv("SHSCODE_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_bbb")
        tok, mode = ai.resolve_github_token()
        assert tok == "ghp_bbb" and mode == "pat"

        monkeypatch.setenv("SHSCODE_GITHUB_TOKEN", "ghp_aaa")
        tok, mode = ai.resolve_github_token()
        assert tok == "ghp_aaa" and mode == "pat"   # SHSCODE_ wins over GITHUB_

    def test_app_jwt_shape(self):
        pytest.importorskip("jwt")
        import time as _t
        from app.git_providers.agent_identity import mint_app_jwt
        # generate a throwaway RSA key
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        token = mint_app_jwt("123456", pem)
        import jwt as pyjwt
        payload = pyjwt.decode(
            token, options={"verify_signature": False})
        assert payload["iss"] == "123456"
        assert payload["exp"] - payload["iat"] <= 660


class TestGitHubProviderCommit:
    def _init_repo(self, tmp_path):
        def git(*args):
            subprocess.run(["git"] + list(args), cwd=tmp_path, check=True,
                           capture_output=True, text=True,
                           env={**os.environ,
                                "GIT_AUTHOR_NAME": "Test User",
                                "GIT_AUTHOR_EMAIL": "t@t.local",
                                "GIT_COMMITTER_NAME": "Test User",
                                "GIT_COMMITTER_EMAIL": "t@t.local"})
        git("init", "-q", "-b", "main")
        (tmp_path / "a.txt").write_text("hello")
        git("add", "-A")
        git("commit", "-qm", "init")
        return git

    def test_commit_adds_agent_trailer(self, tmp_path):
        from app.git_providers.github_provider import GitHubProvider
        self._init_repo(tmp_path)
        (tmp_path / "b.txt").write_text("new work")
        gh = GitHubProvider(repo_dir=str(tmp_path))
        out = gh.commit("feat: add b")
        assert out["committed"] is True
        # the commit message carries both footer and trailer
        assert "Generated with SHS-Code" in out["message"]
        assert "Co-Authored-By: SHS-Code-Agent" in out["message"]
        # verify on the git level too
        proc = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"], cwd=tmp_path,
            capture_output=True, text=True)
        assert "Co-Authored-By: SHS-Code-Agent" in proc.stdout

    def test_commit_without_credit(self, tmp_path):
        from app.git_providers.github_provider import GitHubProvider
        self._init_repo(tmp_path)
        (tmp_path / "c.txt").write_text("x")
        gh = GitHubProvider(repo_dir=str(tmp_path))
        out = gh.commit("chore: no credit", credit_agent=False)
        assert "Co-Authored-By" not in out["message"]

    def test_branch_and_log(self, tmp_path):
        from app.git_providers.github_provider import GitHubProvider
        self._init_repo(tmp_path)
        gh = GitHubProvider(repo_dir=str(tmp_path))
        out = gh.branch("feature-x")
        assert out["branch"] == "feature-x"
        assert gh.current_branch() == "feature-x"
        commits = gh.log(5)
        assert len(commits) >= 1
        assert all("sha" in c and "subject" in c for c in commits)

    def test_stash_roundtrip(self, tmp_path):
        from app.git_providers.github_provider import GitHubProvider
        self._init_repo(tmp_path)
        (tmp_path / "a.txt").write_text("modified")
        gh = GitHubProvider(repo_dir=str(tmp_path))
        assert gh.status_porcelain() != ""
        gh.stash()
        assert gh.status_porcelain() == ""
        gh.stash(pop=True)
        assert gh.status_porcelain() != ""

    def test_push_token_never_stored_in_remote(self, tmp_path, monkeypatch):
        """The push helper authenticates via a one-shot URL — the stored
        remote must never contain the token."""
        from app.git_providers.github_provider import GitHubProvider
        git = self._init_repo(tmp_path)
        # fake remote pointing at github (never contacted — push will fail)
        git("remote", "add", "origin", "https://github.com/example/repo.git")
        monkeypatch.setenv("SHSCODE_GITHUB_TOKEN", "ghp_supersecret")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        gh = GitHubProvider(repo_dir=str(tmp_path))
        with pytest.raises(RuntimeError):
            # offline / nonexistent repo -> push fails; that is fine — we
            # only assert the remote URL was never rewritten with the token
            gh.push(remote="origin", branch="main")
        proc = subprocess.run(["git", "remote", "get-url", "origin"],
                              cwd=tmp_path, capture_output=True, text=True)
        assert "ghp_supersecret" not in proc.stdout
        assert proc.stdout.strip() == "https://github.com/example/repo.git"
