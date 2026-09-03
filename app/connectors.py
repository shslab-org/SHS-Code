from __future__ import annotations

"""
SHS Code — Platform Connectors
==============================
(spec §26, §27) Generic connector layer: platform + username + email + token
+ extra config, persisted at ~/.shscode/connectors.json.

Purpose is NOT merely storing credentials: the connector layer feeds tokens
into the corresponding tool/provider layers (git_providers, integrations,
messaging) so "GitHub connector configured" + "create a repo and push" works
end-to-end.

Security (spec §27): tokens are masked in every display path (mask_token),
never written to the journal, never logged at INFO level.
"""

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger
from app import env

_HOME = env.home_dir()
CONNECTORS_PATH = _HOME / "connectors.json"

KNOWN_PLATFORMS = [
    "github", "gitlab", "bitbucket", "forgejo", "azure-devops",
    "discord", "slack", "telegram", "matrix", "email", "google",
    "linear", "jira", "huggingface", "nvidia", "anthropic", "openai",
]

_FIELDS = {"platform", "username", "email", "token", "api_key", "base_url", "config", "enabled", "added_at"}


def mask_token(token: Optional[str]) -> str:
    """github_pat_11ABCD****ef01 — never expose raw secrets (spec §27)."""
    if not token:
        return "(not set)"
    t = str(token)
    if len(t) <= 8:
        return "*" * len(t)
    return f"{t[:8]}{'*' * 6}{t[-4:]}"


class ConnectorRegistry:
    """Persistent, thread-safe registry of platform connectors."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else CONNECTORS_PATH
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence (atomic)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        self._data = raw
                except Exception as e:
                    logger.error(f"[Connectors] load failed: {e}")
                    self._data = {}

    def _save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, platform: str, username: str = "", email: str = "",
            token: str = "", api_key: str = "", base_url: str = "",
            config: Optional[Dict[str, Any]] = None,
            enabled: bool = True) -> Dict[str, Any]:
        platform = platform.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", platform):
            raise ValueError(f"invalid platform name: {platform!r}")
        entry = {
            "platform": platform,
            "username": username,
            "email": email,
            "token": token or api_key,
            "base_url": base_url,
            "config": config or {},
            "enabled": enabled,
            "added_at": self._data.get(platform, {}).get("added_at") or None,
        }
        import time as _t
        if not entry["added_at"]:
            entry["added_at"] = _t.time()
        self._data[platform] = entry
        self._save()
        logger.info(f"[Connectors] added/updated connector: {platform}")
        return entry

    def remove(self, platform: str) -> bool:
        with self._lock:
            if platform in self._data:
                del self._data[platform]
                self._save()
                return True
            return False

    def get(self, platform: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            c = self._data.get(platform.strip().lower())
            return dict(c) if c else None

    def set_enabled(self, platform: str, enabled: bool) -> bool:
        with self._lock:
            c = self._data.get(platform.strip().lower())
            if c:
                c["enabled"] = enabled
                self._save()
                return True
            return False

    def list(self, masked: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for c in self._data.values():
                c2 = dict(c)
                if masked:
                    c2["token"] = mask_token(c2.get("token"))
                out.append(c2)
            return out

    # ------------------------------------------------------------------
    # Consumption layer — feed real tools (spec §26)
    # ------------------------------------------------------------------

    def get_token(self, platform: str) -> Optional[str]:
        """Raw token for internal use by tools. Returns None if not set/enabled."""
        with self._lock:
            c = self._data.get(platform.strip().lower())
            if c and c.get("enabled") and c.get("token"):
                return c["token"]
            return None

    def apply_to_git_providers(self, cfg: Any) -> int:
        """Wire connector tokens into GitProvidersConfig when the config file
        did not provide them. Returns number of fields injected."""
        injected = 0
        mapping = {
            "github_token": "github",
            "gitlab_token": "gitlab",
            "azure_devops_token": "azure-devops",
            "bitbucket_app_password": "bitbucket",
            "forgejo_token": "forgejo",
        }
        gp = getattr(cfg, "git_providers", None)
        if gp is None:
            return 0
        for field, platform in mapping.items():
            if not getattr(gp, field, None):
                tok = self.get_token(platform)
                if tok:
                    try:
                        setattr(gp, field, tok)
                        injected += 1
                    except Exception:
                        pass
        # bitbucket needs username too
        if getattr(gp, "bitbucket_app_password", None) and not getattr(gp, "bitbucket_username", None):
            c = self.get("bitbucket")
            if c and c.get("username"):
                try:
                    gp.bitbucket_username = c["username"]
                except Exception:
                    pass
        return injected


_registry: Optional[ConnectorRegistry] = None


def get_connectors() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry
