from __future__ import annotations

"""
SHS Code — Custom Provider Registry
===================================
(spec §16, §17) Users can add unlimited custom AI providers (OpenAI-style
or other supported protocols) at runtime. Persisted at
~/.shscode/providers.json — survives restarts.

A provider entry:
  name        unique id (e.g. "my-nim")
  api_type    openai-compat (default) | openai | anthropic | google | ollama | gguf | hf
  base_url    endpoint (required for openai-compat)
  api_key     secret (masked in display)
  model       default model id
  models      optional list of known model ids (for /models)
  rpm         optional rolling-window rate limit (0/None = unlimited unless NIM)
  timeout_s   per-request timeout
  max_retries retry count
  headers     extra HTTP headers
  max_tokens / temperature
  enabled     bool

Integration: `provider_overlay()` merges a registry entry into the live
LLMConfig so LLM.switch() can rebuild the backend with it (spec §4: switch
must never destroy context — switching only rebuilds the backend; message
history lives in agent memory and is untouched).
"""

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.connectors import mask_token
from app.logger import logger
from app import env

_HOME = env.home_dir()
PROVIDERS_PATH = _HOME / "providers.json"

API_TYPES = {"openai-compat", "openai", "anthropic", "google", "ollama",
             "gguf", "hf", "huggingface"}

# Known model catalogs (for /models display when a custom provider doesn't
# enumerate models). Only used for hints — never restricts what user can set.
KNOWN_MODELS: Dict[str, List[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini", "o1"],
    "anthropic": ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest",
                  "claude-3-5-haiku-latest"],
    "google": ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro"],
    "mistral": ["mistral-large-latest", "codestral-latest", "mistral-small-latest"],
    "nvidia": ["meta/llama-3.1-405b-instruct", "meta/llama-3.1-70b-instruct",
               "deepseek-ai/deepseek-r1", "qwen/qwen2.5-coder-32b-instruct"],
    "ollama": ["llama3.2:3b", "qwen2.5-coder:7b", "deepseek-r1:8b"],
}


class ProviderRegistry:
    """Persistent, thread-safe registry of user-defined providers."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else PROVIDERS_PATH
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        self._data = raw
                except Exception as e:
                    logger.error(f"[Providers] load failed: {e}")

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

    def add(self, name: str, api_type: str = "openai-compat", base_url: str = "",
            api_key: str = "", model: str = "", models: Optional[List[str]] = None,
            rpm: Optional[int] = None, timeout_s: int = 1800,
            max_retries: int = 6, headers: Optional[Dict[str, str]] = None,
            max_tokens: int = 4096, temperature: float = 0.0,
            enabled: bool = True) -> Dict[str, Any]:
        name = name.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):
            raise ValueError(f"invalid provider name: {name!r}")
        api_type = (api_type or "openai-compat").strip().lower()
        if api_type in ("hf",):
            api_type = "huggingface"
        if api_type not in API_TYPES:
            raise ValueError(f"api_type must be one of {sorted(API_TYPES)}")
        if api_type == "openai-compat" and not base_url:
            raise ValueError("openai-compat provider requires base_url")
        entry = {
            "name": name,
            "api_type": api_type,
            "base_url": base_url.strip(),
            "api_key": api_key,
            "model": model,
            "models": models or ([model] if model else []),
            "rpm": int(rpm) if rpm else 0,
            "timeout_s": int(timeout_s),
            "max_retries": int(max_retries),
            "headers": headers or {},
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "enabled": enabled,
            "added_at": self._data.get(name, {}).get("added_at") or time.time(),
        }
        self._data[name] = entry
        self._save()
        logger.info(f"[Providers] registered provider: {name} ({api_type})")
        return entry

    def remove(self, name: str) -> bool:
        with self._lock:
            if name in self._data:
                del self._data[name]
                self._save()
                return True
            return False

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            e = self._data.get(name.strip().lower())
            return dict(e) if e else None

    def list(self, masked: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for e in self._data.values():
                e2 = dict(e)
                if masked:
                    e2["api_key"] = mask_token(e2.get("api_key"))
                out.append(e2)
            return out

    def set_enabled(self, name: str, enabled: bool) -> bool:
        with self._lock:
            e = self._data.get(name.strip().lower())
            if e:
                e["enabled"] = enabled
                self._save()
                return True
            return False

    def models_for(self, name: str) -> List[str]:
        e = self.get(name)
        if not e:
            return []
        models = list(e.get("models") or [])
        if models:
            return models
        # NIM-style: model ids from catalog by heuristic
        for key, catalog in KNOWN_MODELS.items():
            if key in name or (e.get("base_url") and key in e["base_url"].lower()):
                return catalog
        return []

    # ------------------------------------------------------------------
    # Overlay onto live config (used by LLM.switch / CLI /provider)
    # ------------------------------------------------------------------

    def provider_overlay(self, name: str, cfg: Any) -> bool:
        """Merge registry entry into a live LLMConfig object (in place).
        Returns True when applied."""
        e = self.get(name)
        if not e or not e.get("enabled"):
            return False
        llm = cfg.llm
        api_type = e["api_type"]

        # map registry api_type -> runtime provider id used by LLM._build_backend
        if api_type == "openai-compat":
            llm.provider = "universal"
            llm.base_url = e["base_url"]
        elif api_type == "openai":
            llm.provider = "openai"
            llm.base_url = e.get("base_url") or None
        elif api_type == "anthropic":
            llm.provider = "anthropic"
            llm.base_url = e.get("base_url") or None
        elif api_type == "google":
            llm.provider = "google"
            llm.base_url = None
        elif api_type == "ollama":
            llm.provider = "ollama"
            llm.base_url = e.get("base_url") or "http://localhost:11434"
        elif api_type == "gguf":
            llm.provider = "gguf"
            llm.base_url = None
        elif api_type == "huggingface":
            llm.provider = "huggingface"
            llm.base_url = e.get("base_url") or None

        llm.api_key = e.get("api_key") or llm.api_key
        if e.get("model"):
            llm.model = e["model"]
        llm.max_tokens = e.get("max_tokens", llm.max_tokens)
        llm.temperature = e.get("temperature", llm.temperature)
        llm.timeout = e.get("timeout_s", llm.timeout)
        llm.max_retries = e.get("max_retries", llm.max_retries)
        if e.get("headers"):
            llm.extra_headers = dict(e["headers"])
        # Per-provider custom rate limit (spec §6/§7): entry rpm > 0 overrides
        # the global [llm.rate_limit].rpm for this provider; entry rpm 0
        # restores the global baseline. Provider DEFAULTS (e.g. NIM 40) are
        # resolved later by the limiter when no custom limit applies.
        if getattr(llm, "rate_limit", None) is not None:
            overlay_rpm_apply(llm.rate_limit, e.get("rpm"))
        return True


_registry: Optional[ProviderRegistry] = None

# Baseline global [llm.rate_limit].rpm captured before any per-provider
# overlay mutated it, so switching away from a provider restores the user's
# global setting instead of leaking the previous provider's custom limit.
_overlay_state: Dict[str, Any] = {"base_rpm": None}


def overlay_rpm_apply(rl_cfg: Any, entry_rpm: Any) -> int:
    """Apply a per-provider custom RPM onto the live rate-limit config.

    Precedence (user spec §6/§7):
      entry rpm > 0            -> custom limit for this provider (wins)
      entry rpm 0/absent       -> restore the global baseline
    Returns the effective rpm now set on the config object.
    """
    if _overlay_state["base_rpm"] is None:
        _overlay_state["base_rpm"] = int(getattr(rl_cfg, "rpm", 0) or 0)
    if int(entry_rpm or 0) > 0:
        rl_cfg.rpm = int(entry_rpm)
    else:
        rl_cfg.rpm = int(_overlay_state["base_rpm"] or 0)
    return int(rl_cfg.rpm)


def get_providers() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
