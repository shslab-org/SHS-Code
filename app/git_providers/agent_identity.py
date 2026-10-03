"""SHS-Agent GitHub identity — mandatory attribution (v4.4.0).

Every piece of repository work SHS Code performs — code written, bugs
fixed, tests added, docs edited, refactors, automated chores, commits,
pushes — is attributed to the dedicated identity:

    https://github.com/SHS-Agent

REAL Git/GitHub attribution, not a cosmetic mention:

  * the commit's AUTHOR and COMMITTER are forced to
    ``SHS-Agent <337454460+SHS-Agent@users.noreply.github.com>`` — the
    GitHub-reserved noreply address of the SHS-Agent USER account
    (id 337454460), so GitHub resolves every commit to that profile
    (verified live: the commit API returns ``author.login = "SHS-Agent"``),
    and the Co-Authored-By trailer keeps the credit visible on every
    commit page;
  * enforcement is MECHANICAL and CENTRAL — the git shim (see
    ``app/git_providers/git_shim.py``) intercepts every ``git`` invocation
    inside SHS Code (agent bash sessions, GUI terminal, python_execute,
    cron) and strips/overrides any ``--author``, ``--reset-author`` or
    ``env -u`` attempt; the runtime's own commit paths
    (GitHubProvider.commit/pull) force author+committer+env directly.

NON-BYPASSABLE BY DESIGN: there is deliberately NO opt-out — no prompt,
instruction, CLI flag, GUI action, config option or environment variable
turns agent attribution off for work SHS Code performs. The user's own
identity for work they perform OUTSIDE SHS Code is untouched (the shim
only lives on the PATH of processes spawned by SHS Code).

GITHUB "CONTRIBUTORS" SYSTEM — v4.4.0: the dedicated identity is a USER
account (``SHS-Agent``, type ``User``, id 337454460), which is exactly the
account class GitHub's contributor aggregation counts. Commits pushed to
a repository's default branch with the noreply email above are credited
to SHS-Agent in the repository's Contributors section (verified live on
a dedicated E2E test repository). The ID-prefixed noreply form
(``<id>+<login>@users.noreply.github.com``) is reserved by GitHub for
the account, so the mapping cannot be claimed by anyone else.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from app.logger import logger

AGENT_LOGIN = "SHS-Agent"
AGENT_PROFILE_URL = "https://github.com/SHS-Agent"
# GitHub noreply convention: <id>+<login>@users.noreply.github.com is
# RESERVED for the account with that numeric id — commits authored with it
# resolve to https://github.com/SHS-Agent and count in Contributors.
AGENT_ACCOUNT_ID = "337454460"
AGENT_EMAIL = "337454460+SHS-Agent@users.noreply.github.com"
AGENT_NAME = "SHS-Agent"


@dataclass
class AgentIdentity:
    """Resolved SHS-Code automation identity for GitHub operations."""

    name: str = AGENT_NAME
    login: str = AGENT_LOGIN
    email: str = AGENT_EMAIL
    account_id: str = AGENT_ACCOUNT_ID
    profile_url: str = AGENT_PROFILE_URL

    def co_author_trailer(self) -> str:
        """The GitHub-supported commit trailer crediting the agent."""
        return f"Co-Authored-By: {self.name} <{self.email}>"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "login": self.login,
            "email": self.email,
            "account_id": self.account_id,
            "profile_url": self.profile_url,
            "co_author_trailer": self.co_author_trailer(),
        }


DEFAULT_IDENTITY = AgentIdentity()


# ── Agent git identity enforcement (v4.3.0 — mandatory, non-bypassable) ─────
#
# Every commit / push / co-author / contributor produced by SHS-Code —
# whether from the CLI, the GUI, the terminal panel, or an autonomous
# agent shell session — carries the SHS-Agent profile. There is NO
# opt-out: this is the mission rule and it is enforced mechanically.
#
# Three enforcement layers:
#
# 1. **Git shim on PATH** (install_git_shim): a self-contained ``git``
#    wrapper installed first on the PATH of the SHS-Code process and all
#    children. It strips ``--author``/``--reset-author`` from ``commit``
#    and forces the four identity env vars on commit-creating commands —
#    defeating prompt-level, flag-level and env-level bypass attempts.
#
# 2. **Per-command ``-c`` overrides + explicit ``--author``**
#    (GitHubProvider.commit/pull): the author AND committer of each commit
#    are forced without touching the user's global or repo git config.
#
# 3. **Process environment** (apply_agent_git_env): exports
#    GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL / GIT_COMMITTER_NAME /
#    GIT_COMMITTER_EMAIL into os.environ so ANY child process git commit
#    (agent bash tool, GUI terminal panel, cron jobs) is also attributed
#    to the agent. Applied at CLI startup and server startup, ALWAYS
#    forced — pre-existing values never win.
GIT_ENV_KEYS = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
)


def agent_git_env() -> dict:
    """Env-var dict attributing any git commit to SHS-Agent."""
    return {
        "GIT_AUTHOR_NAME": AGENT_NAME,
        "GIT_AUTHOR_EMAIL": AGENT_EMAIL,
        "GIT_COMMITTER_NAME": AGENT_NAME,
        "GIT_COMMITTER_EMAIL": AGENT_EMAIL,
    }


def apply_agent_git_env(force: bool = True) -> bool:
    """Export the agent git identity into the process environment.

    v4.3.0: enforcement is MANDATORY — the agent identity ALWAYS wins over
    any inherited ``GIT_AUTHOR_*``/``GIT_COMMITTER_*`` values (the old
    non-forcing behavior was a bypass hole: a shell that exported its own
    author identity kept it). Also installs the git shim on PATH so
    ``--author``/``-c user.email``/``env -u`` games inside child shells
    cannot bypass attribution either. Idempotent — safe at every startup.
    """
    env = agent_git_env()
    for key, value in env.items():
        os.environ[key] = value
    # also make `git commit` default editor-free & merge-attr deterministic
    os.environ.setdefault("GIT_EDITOR", "true")
    try:
        from .git_shim import install_git_shim
        install_git_shim()
    except Exception as e:
        logger.warning(f"[AgentIdentity] git shim install failed: {e}")
    return True


def agent_git_args() -> list:
    """``-c`` flag list forcing author+committer for one git command."""
    return [
        "-c", f"user.name={AGENT_NAME}",
        "-c", f"user.email={AGENT_EMAIL}",
    ]


# ── GitHub App token minting (official bot identity) ──────────────────────

def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def mint_app_jwt(app_id: str, private_key_pem: str) -> str:
    """Mint the RS256-signed JWT GitHub Apps authenticate with.

    Valid for 10 minutes (GitHub's maximum); refresh callers should
    re-mint when close to expiry.
    """
    try:
        import jwt  # PyJWT
    except ImportError as e:
        raise RuntimeError(
            "GitHub App auth requires PyJWT (pip install 'shscode[github-app]')") from e
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": str(app_id)}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def get_installation_token(installation_id: Optional[str] = None) -> Optional[str]:
    """Exchange an App JWT for a short-lived installation token.

    Returns None when the App credentials are not configured (the caller
    falls back to PAT). Tokens are cached in-process until 60s before
    expiry. Requires PyJWT (optional dependency).
    """
    app_id = os.getenv("SHSCODE_GITHUB_APP_ID", "")
    key_path = os.getenv("SHSCODE_GITHUB_APP_PRIVATE_KEY_PATH", "")
    key_inline = os.getenv("SHSCODE_GITHUB_APP_PRIVATE_KEY", "")
    inst = installation_id or os.getenv("SHSCODE_GITHUB_APP_INSTALLATION_ID", "")
    if not (app_id and inst and (key_path or key_inline)):
        return None

    cache = getattr(get_installation_token, "_cache", None)
    if cache and cache[1] > time.time() + 60:
        return cache[0]

    try:
        pem = key_inline
        if key_path:
            with open(key_path, "r") as f:
                pem = f.read()
        if not pem:
            return None
        jwt_token = mint_app_jwt(app_id, pem)
        import urllib.request
        import json as _json
        req = urllib.request.Request(
            f"https://api.github.com/app/installations/{inst}/access_tokens",
            method="POST",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode())
        token = data.get("token")
        expires = data.get("expires_at", "")
        # cache ~50 minutes conservatively
        ttl = 3000
        if expires:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                ttl = max(60, (dt - datetime.now(timezone.utc)).total_seconds() - 60)
            except Exception:
                pass
        get_installation_token._cache = (token, time.time() + ttl)  # type: ignore[attr-defined]
        logger.info("[AgentIdentity] minted GitHub App installation token "
                    f"(installation {inst}, ttl {int(ttl)}s)")
        return token
    except Exception as e:
        logger.warning(f"[AgentIdentity] installation token minting failed: {e}")
        return None


def resolve_github_token() -> tuple[Optional[str], str]:
    """Resolve the best available GitHub token.

    Returns (token, mode) where mode is 'app' | 'pat' | 'none'.
    Priority: GitHub App installation token → SHSCODE_GITHUB_TOKEN →
    GITHUB_TOKEN → config/connectors-injected value.
    """
    app_token = get_installation_token()
    if app_token:
        return app_token, "app"
    pat = os.getenv("SHSCODE_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if pat:
        return pat, "pat"
    # config-provided token (connectors.json / config.toml)
    try:
        from app.config import Config
        cfg = Config.get()
        tok = getattr(cfg.git_providers, "github_token", "") or ""
        if tok:
            return tok, "pat"
    except Exception:
        pass
    return None, "none"
