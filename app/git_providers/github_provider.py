"""GitHubProvider — the centralized GitHub facade for SHS-Code (v4.0.1, mission §17).

    SHS-Code  (CLI ─ GUI ─ agent tools)
        │
        └── GitHubProvider          ← this module
                │
                ├── git operations  (clone / branch / commit / push / pull
                │                    via the git CLI, with agent attribution)
                │
                ├── GitHubService   (API: PRs, issues, reviews, repos)
                │
                └── SHS-Code-Agent identity
                        (GitHub App token when configured, else PAT;
                         Co-Authored-By trailer on every commit)

Both the CLI (/github) and the GUI (/github/* endpoints) call THIS
class — there is exactly one implementation of GitHub behavior.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from app.logger import logger

from .agent_identity import (
    AgentIdentity, DEFAULT_IDENTITY, resolve_github_token, AGENT_PROFILE_URL,
    agent_git_args, agent_git_env,
)


def _git(args: list[str], cwd: Optional[str] = None,
         timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command, raising RuntimeError with stderr on failure."""
    proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args[:3])} failed: {proc.stderr.strip()[:400]}")
    return proc


class GitHubProvider:
    """Unified GitHub operations with SHS-Code-Agent attribution."""

    def __init__(self, identity: Optional[AgentIdentity] = None,
                 repo_dir: Optional[str] = None):
        self.identity = identity or DEFAULT_IDENTITY
        self.repo_dir = repo_dir or os.getcwd()
        self._service: Any = None

    # ── auth / status ─────────────────────────────────────────────────────

    def _token(self) -> tuple[Optional[str], str]:
        return resolve_github_token()

    def _svc(self):
        """Lazily build the GitHubService (API operations)."""
        if self._service is None:
            from .models import AuthInfo, AuthType
            from .github.service import GitHubService
            from .provider import GitProviderRouter
            token, mode = self._token()
            auth = AuthInfo(
                auth_type=AuthType.APP_TOKEN if mode == "app" else AuthType.PERSONAL_ACCESS_TOKEN,
                token=token or "",
            )
            self._service = GitHubService(auth)
        return self._service

    def status(self) -> dict:
        """Auth + attribution status for the GUI/CLI."""
        token, mode = self._token()
        out = {
            "identity": self.identity.as_dict(),
            "auth_mode": mode,
            "authenticated": bool(token),
        }
        if token:
            try:
                user = self._svc().get_authenticated_user()
                out["account"] = {
                    "login": user.get("login", ""),
                    "type": user.get("type", ""),
                    "url": user.get("html_url", ""),
                }
            except Exception as e:
                out["account_error"] = str(e)[:200]
        return out

    # ── local git operations (with agent attribution) ──────────────────────

    def _ensure_repo(self) -> str:
        probe = _git(["rev-parse", "--is-inside-work-tree"], cwd=self.repo_dir)
        if probe.stdout.strip() != "true":
            raise RuntimeError(f"{self.repo_dir} is not a git repository")
        return self.repo_dir

    def clone(self, url: str, dest: Optional[str] = None) -> str:
        """Clone a repository. Authenticated URLs are rewritten with the
        resolved token so private repos work; the token never appears in
        the returned URL."""
        dest = dest or url.rstrip("/").split("/")[-1].replace(".git", "")
        token, mode = self._token()
        fetch_url = url
        if token and url.startswith("https://github.com/"):
            fetch_url = url.replace(
                "https://", f"https://x-access-token:{token}@", 1)
        _git(["clone", fetch_url, dest], timeout=600)
        # scrub the token from the remote URL immediately after cloning
        try:
            _git(["remote", "set-url", "origin", url], cwd=dest)
        except Exception:
            pass
        logger.info(f"[GitHubProvider] cloned {url} → {dest} (auth={mode})")
        return dest

    def branch(self, name: str, from_ref: str = "HEAD") -> dict:
        self._ensure_repo()
        _git(["checkout", "-B", name, from_ref], cwd=self.repo_dir)
        return {"branch": name, "from": from_ref}

    def current_branch(self) -> Optional[str]:
        try:
            proc = _git(["rev-parse", "--abbrev-ref", "HEAD"],
                        cwd=self.repo_dir, check=False)
            return proc.stdout.strip() if proc.returncode == 0 else None
        except Exception:
            return None

    def status_porcelain(self) -> str:
        try:
            proc = _git(["status", "--porcelain"], cwd=self.repo_dir)
            return proc.stdout.strip()
        except Exception:
            return ""

    def diff(self, staged: bool = False, max_chars: int = 20000) -> str:
        args = ["diff", "--cached"] if staged else ["diff"]
        proc = _git(args, cwd=self.repo_dir)
        return proc.stdout[:max_chars]

    def add(self, paths: Optional[list[str]] = None) -> dict:
        self._ensure_repo()
        paths = paths or ["-A"]
        _git(["add"] + paths, cwd=self.repo_dir)
        return {"added": paths}

    def commit(self, message: str, add_all: bool = True,
               credit_agent: bool = True) -> dict:
        """Commit staged/all changes attributed to SHS-Code-Agent.

        v4.2.0 ("sab jagah" rule): the commit AUTHOR and COMMITTER are
        forced to the agent identity via per-command ``-c`` overrides
        (the user's global git config is never touched), so the commit
        list and contributor graph on GitHub show SHS-Code-Agent. The
        message additionally keeps the Co-Authored-By trailer and the
        'Generated with SHS-Code' footer for visible credit everywhere.
        """
        self._ensure_repo()
        if add_all:
            _git(["add", "-A"], cwd=self.repo_dir)
        full_message = message.strip()
        if credit_agent:
            full_message += (
                f"\n\nGenerated with SHS-Code\n{self.identity.co_author_trailer()}")
        proc = _git(agent_git_args() + ["commit", "-m", full_message],
                    cwd=self.repo_dir)
        sha = ""
        try:
            sha = _git(["rev-parse", "HEAD"], cwd=self.repo_dir).stdout.strip()
        except Exception:
            pass
        author = ""
        try:
            author = _git(["log", "-1", "--pretty=format:%an <%ae>"],
                          cwd=self.repo_dir).stdout.strip()
        except Exception:
            pass
        return {"committed": True, "sha": sha[:12],
                "message": full_message, "author": author,
                "output": proc.stdout.strip()[:200]}

    def push(self, remote: str = "origin", branch: Optional[str] = None,
             set_upstream: bool = False) -> dict:
        """Push the branch. Injects the token into the push URL for this
        one command only — the stored remote URL is never rewritten."""
        self._ensure_repo()
        branch = branch or self.current_branch()
        token, mode = self._token()
        if token:
            # push via a one-shot authenticated URL; stored remote untouched
            remote_url = _git(["remote", "get-url", remote],
                              cwd=self.repo_dir).stdout.strip()
            if remote_url.startswith("https://github.com/") or \
               remote_url.startswith("https://"):
                push_url = remote_url.replace(
                    "https://", f"https://x-access-token:{token}@", 1)
                args = ["push", push_url]
                if set_upstream and branch:
                    args.append(f"HEAD:refs/heads/{branch}")
                proc = _git(args, cwd=self.repo_dir, timeout=300)
                return {"pushed": True, "branch": branch,
                        "output": proc.stdout.strip()[:300]}
        args = ["push", remote] + ([branch] if branch else [])
        if set_upstream:
            args.insert(1, "-u")
        proc = _git(args, cwd=self.repo_dir, timeout=300)
        return {"pushed": True, "branch": branch,
                "output": (proc.stdout + proc.stderr).strip()[:300]}

    def pull(self, remote: str = "origin", branch: Optional[str] = None) -> dict:
        """Pull remote changes. Any merge commit the pull creates is
        attributed to SHS-Code-Agent (author + committer via -c flags
        and the process env) — v4.2.0 "sab jagah" rule."""
        self._ensure_repo()
        args = agent_git_args() + ["pull", remote] + ([branch] if branch else [])
        proc = subprocess.run(
            ["git"] + args, cwd=self.repo_dir, capture_output=True,
            text=True, timeout=300, env={**os.environ, **agent_git_env()})
        return {"pulled": proc.returncode == 0,
                "output": (proc.stdout + proc.stderr).strip()[:300]}

    def stash(self, pop: bool = False) -> dict:
        self._ensure_repo()
        _git(["stash", "pop"] if pop else ["stash"], cwd=self.repo_dir)
        return {"stashed": not pop, "popped": pop}

    def log(self, limit: int = 10) -> list[dict]:
        self._ensure_repo()
        proc = _git(["log", f"-{int(limit)}", "--pretty=format:%h¦%an¦%s"],
                    cwd=self.repo_dir)
        out = []
        for line in proc.stdout.splitlines():
            parts = line.split("¦")
            if len(parts) == 3:
                out.append({"sha": parts[0], "author": parts[1], "subject": parts[2]})
        return out

    # ── GitHub API operations (via GitHubService) ─────────────────────────

    def create_pr(self, repo_id: str, title: str, body: str,
                  head: str, base: str = "main", draft: bool = False) -> dict:
        pr = self._svc().create_pr(repo_id, title, body, head, base, draft=draft)
        return {"number": getattr(pr, "number", None),
                "url": getattr(pr, "url", ""),
                "title": getattr(pr, "title", title)}

    def list_prs(self, repo_id: str, state: str = "open", limit: int = 20) -> list:
        prs = self._svc().get_pull_requests(repo_id, state=state)
        return [
            {"number": p.number, "title": p.title, "state": p.state,
             "author": getattr(p, "author", ""), "url": getattr(p, "url", "")}
            for p in prs[:limit]
        ]

    def list_issues(self, repo_id: str, state: str = "open", limit: int = 20) -> list:
        issues = self._svc().get_issues(repo_id, state=state)
        return [
            {"number": i.number, "title": i.title, "state": i.state,
             "url": getattr(i, "url", "")}
            for i in issues[:limit]
        ]

    def create_issue(self, repo_id: str, title: str, body: str) -> dict:
        issue = self._svc().create_issue(repo_id, title, body)
        return {"number": getattr(issue, "number", None),
                "url": getattr(issue, "url", "")}

    def comment_on_issue(self, repo_id: str, issue_number: int, body: str) -> dict:
        c = self._svc().comment_on_issue(repo_id, issue_number, body)
        return {"comment_id": getattr(c, "id", None)}

    def list_repos(self, limit: int = 20) -> list:
        repos = self._svc().get_repos()
        return [
            {"id": r.id, "name": r.name, "url": getattr(r, "url", ""),
             "private": getattr(r, "private", False)}
            for r in repos[:limit]
        ]