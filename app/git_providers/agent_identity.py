"""SHS-Code-Agent GitHub identity (v4.0.1 — mission §17).

Central attribution layer for every GitHub action SHS-Code performs.
The automation identity is consistently represented as the
SHS-Code-Agent (https://github.com/SHS-Code-Agent) rather than
pretending the human user performed every action.

Mechanisms (in priority order):

1. **GitHub App installation token** (the official bot-identity
   mechanism): when ``SHSCODE_GITHUB_APP_ID`` +
   ``SHSCODE_GITHUB_APP_PRIVATE_KEY_PATH`` (or ``..._PRIVATE_KEY``) are
   configured, a short-lived RS256-signed JWT is minted and exchanged
   for an installation token against ``SHSCODE_GITHUB_APP_INSTALLATION_ID``.
   Commits pushed with an installation token are attributed by GitHub's
   own machinery; the Co-Authored-By trailer adds the visible agent
   credit on every commit regardless of auth mode.

2. **Personal access token** (``SHSCODE_GITHUB_TOKEN`` / ``GITHUB_TOKEN``
   / connectors): used for API + push auth. The COMMITS still carry the
   Co-Authored-By trailer so the agent credit is honest and visible,
   while the author identity reflects the token's account.

The trailer is the officially GitHub-supported way to credit a
collaborator on a commit:
    Co-Authored-By: SHS-Code-Agent <SHS-Code-Agent@users.noreply.github.com>
GitHub renders the co-author profile link when the email maps to a
GitHub account. We never claim the ORG owns every commit — attribution
follows GitHub's actual model.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from app.logger import logger

AGENT_LOGIN = "SHS-Code-Agent"
AGENT_PROFILE_URL = "https://github.com/SHS-Code-Agent"
# GitHub noreply convention for bot-ish accounts:
# <login>@users.noreply.github.com — maps the trailer to the profile.
AGENT_EMAIL = "SHS-Code-Agent@users.noreply.github.com"
AGENT_NAME = "SHS-Code-Agent"


@dataclass
class AgentIdentity:
    """Resolved SHS-Code automation identity for GitHub operations."""

    name: str = AGENT_NAME
    login: str = AGENT_LOGIN
    email: str = AGENT_EMAIL
    profile_url: str = AGENT_PROFILE_URL

    def co_author_trailer(self) -> str:
        """The GitHub-supported commit trailer crediting the agent."""
        return f"Co-Authored-By: {self.name} <{self.email}>"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "login": self.login,
            "email": self.email,
            "profile_url": self.profile_url,
            "co_author_trailer": self.co_author_trailer(),
        }


DEFAULT_IDENTITY = AgentIdentity()


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
