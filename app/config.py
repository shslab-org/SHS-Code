from __future__ import annotations

"""
SHS Code Configuration System
================================
Config loads in priority order (highest first):
  1. Environment variables
  2. ~/.shscode/profiles/<SHSCODE_PROFILE>/.env
  3. ~/.shscode/profiles/<SHSCODE_PROFILE>/config.yaml
  4. ~/.shscode/.env
  5. ~/.shscode/config.yaml
  6. ./config.toml  (legacy)
  7. Built-in defaults (MockLLM — safe for immediate use)
"""

import os
import threading
from enum import Enum
from pathlib import Path
from typing import Optional, get_args

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from pydantic import BaseModel, Field, model_validator
from app.exceptions import ConfigError
from app import env

import logging as _stdlib_logging

# config must NOT import app.logger: app.logger's module level calls
# Config.get() — a lazy import inside _load would deadlock on the class
# lock (found live during v4.3.0 development). Stdlib logger only; the
# app logger attaches its own handlers later and these records propagate.
_logger = lambda: _stdlib_logging.getLogger("shscode.config")

_HOME = env.home_dir()


class AppEnv(str, Enum):
    DEV  = "dev"
    PROD = "prod"
    TEST = "test"


class LLMStreamingConfig(BaseModel):
    enabled:       bool = True
    buffer_size:   int  = 4096
    chunk_timeout: int  = 30


class LLMFallbackConfig(BaseModel):
    enabled:             bool          = False
    chain:               list[str]     = Field(default_factory=lambda: ["gpt-4o", "claude-3-5-sonnet"])
    cooldown_s:          float         = 60.0
    cooldown_multiplier: float         = 2.0
    max_cooldown_s:      float         = 600.0
    triggers:            list[str]     = Field(default_factory=lambda: ["rate_limit", "service_unavailable", "context_window", "quota"])


class LLMRateLimitConfig(BaseModel):
    """Rolling-window request pacing (spec §18/§19).
    rpm=0 means unlimited EXCEPT auto-detected NVIDIA NIM endpoints (40 RPM default)."""
    enabled: bool = True
    rpm:     int  = 0


class LLMConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    provider:       str            = "mock"
    model:          str            = "gpt-4o"
    base_url:       Optional[str]  = None
    api_key:        Optional[str]  = None
    max_tokens:     int            = 4096
    temperature:    float          = 0.0
    max_retries:    int            = 15
    # None = timeout not explicitly configured -> adaptive default applies
    # (long-thinking models 1800s, regular models 600s). ANY explicit value is
    # honored exactly by the runtime — never clamped (regression fix).
    timeout:        Optional[int]  = None
    extra_headers:  dict[str, str] = Field(default_factory=dict)
    extra_api_keys: list[str]      = Field(default_factory=list)
    streaming:      LLMStreamingConfig = Field(default_factory=LLMStreamingConfig)
    fallback:       LLMFallbackConfig  = Field(default_factory=LLMFallbackConfig)
    rate_limit:     LLMRateLimitConfig = Field(default_factory=LLMRateLimitConfig)

    @model_validator(mode="after")
    def _coerce_provider(self) -> "LLMConfig":
        safe = {"mock", "ollama", "lmstudio", "openai-compat", "universal", "gguf", "huggingface", "hf", ""}
        # FIX: Only silently coerce to mock if provider is NOT a known real provider.
        # Previously, valid providers like "openai", "anthropic" were silently
        # changed to "mock" when no API key was present in the config file,
        # even though environment variables might provide keys later.
        # Now we only coerce truly unknown/empty providers.
        known_providers = {"openai", "anthropic", "google", "gemini", "mistral", "bedrock"}
        if self.provider not in safe and self.provider not in known_providers and not self.api_key and not self.base_url:
            self.provider = "mock"
        return self


class BrowserConfig(BaseModel):
    headless:           bool = True
    disable_security:   bool = False
    max_content_length: int  = 10_000


class SearchConfig(BaseModel):
    engines:     list[str] = Field(default_factory=lambda: ["duckduckgo", "bing"])
    max_results: int        = 10

    @model_validator(mode="after")
    def _normalize(self) -> "SearchConfig":
        valid = {"duckduckgo", "bing", "google"}
        self.engines = [e.lower().strip() for e in self.engines
                        if e.lower().strip() in valid]
        if not self.engines:
            self.engines = ["duckduckgo", "bing"]
        return self


class SandboxConfig(BaseModel):
    enabled:      bool = False
    docker_image: str  = "python:3.11-slim"
    memory_limit: str  = "256m"
    timeout:      int  = 30


class MCPServerDef(BaseModel):
    name:      str
    transport: str           = "stdio"
    command:   Optional[str] = None
    args:      list[str]     = Field(default_factory=list)
    url:       Optional[str] = None


class RunFlowConfig(BaseModel):
    enable_data_analysis: bool = False
    timeout:              int  = 3600


class LoggingConfig(BaseModel):
    level:          str  = "DEBUG"
    # v3.0.3: console gets its own level so internal DEBUG/TRACE diagnostics
    # (tool-selector scoring bars, retry internals) never spam the terminal.
    # File log keeps the full `level`. Default WARNING: the terminal shows only
    # things that need attention; progress UX comes from the spinner/activity
    # feed, and full detail lives in the file log (/log, logs/*.log).
    # Set console_level = "DEBUG" to see everything.
    console_level:  str  = "WARNING"
    json_format:    bool = False
    include_trace:  bool = True
    redact_secrets: bool = False


class SkinsConfig(BaseModel):
    active:       str = "default"
    border_color: str = "#FFD700"


class SecurityConfig(BaseModel):
    enabled:                bool       = True
    analyzers:              list[str]  = Field(default_factory=lambda: ["pattern", "rails"])
    confirmation_threshold: str        = "medium"
    cipher_key:             Optional[str] = None


class HooksConfig(BaseModel):
    enabled:   bool       = True
    auto_load: bool       = True
    hook_dirs: list[str]  = Field(default_factory=lambda: ["~/.shscode/hooks"])
    timeout_s: int        = 30


class SSHConfig(BaseModel):
    """SSH remote gateway (documented in the example config.toml; v4.3.0
    gives it a real schema so the section is first-class instead of
    silently ignored by pydantic's extra='ignore')."""
    enabled:            bool          = False
    port:               int           = 2222
    host:               str           = "0.0.0.0"
    host_key_path:      Optional[str] = "~/.shscode/ssh/host_key"
    authorized_keys_path: Optional[str] = "~/.shscode/ssh/authorized_keys"


class ContextConfig(BaseModel):
    max_events:     int  = 200
    max_tokens:     int  = 80000
    condenser_type: str  = "rolling"


class ConversationConfig(BaseModel):
    max_iterations:    int  = 30
    confirmation_mode: str  = "confirm_risky"
    stuck_detection:   bool = True
    stuck_threshold:   int  = 3


class ObservabilityConfig(BaseModel):
    tracing_enabled:  bool  = False
    tracing_endpoint: str   = "http://localhost:4317"
    tracing_service:  str   = "shscode"
    metrics_enabled:  bool  = False
    metrics_port:     int   = 9090
    health_enabled:   bool  = True
    health_path:      str   = "/health"


class SecretsConfig(BaseModel):
    backend:           Optional[str] = "file"
    file_path:         Optional[str] = None
    encryption_enabled: bool         = True


class FileStoreConfig(BaseModel):
    backend:    str           = "local"
    base_dir:   Optional[str] = None
    s3_bucket:  Optional[str] = None
    s3_region:  str           = "us-east-1"
    s3_endpoint: Optional[str] = None
    gcs_bucket: Optional[str] = None


class GitProvidersConfig(BaseModel):
    default_provider:      str           = "github"
    github_token:          Optional[str] = None
    gitlab_token:          Optional[str] = None
    gitlab_url:            str           = "https://gitlab.com"
    azure_devops_token:    Optional[str] = None
    azure_devops_org:      Optional[str] = None
    bitbucket_username:    Optional[str] = None
    bitbucket_app_password: Optional[str] = None
    forgejo_url:           Optional[str] = None
    forgejo_token:         Optional[str] = None


class IntegrationsConfig(BaseModel):
    jinja_templates_dir: str           = "~/.shscode/templates"
    webhooks_enabled:    bool          = False
    webhook_secret:      Optional[str] = None


class ParallelExecutorConfig(BaseModel):
    max_workers: int   = 4
    timeout_s:   int   = 300


class MigrationsConfig(BaseModel):
    enabled:     bool          = True
    auto_run:    bool          = False
    database_url: Optional[str] = None


class AppConfig(BaseModel):
    env:                  AppEnv          = AppEnv.DEV
    llm:                  LLMConfig               = Field(default_factory=LLMConfig)
    browser:              BrowserConfig            = Field(default_factory=BrowserConfig)
    search:               SearchConfig             = Field(default_factory=SearchConfig)
    sandbox:              SandboxConfig            = Field(default_factory=SandboxConfig)
    mcp_servers:          list[MCPServerDef]        = Field(default_factory=list)
    runflow:              RunFlowConfig            = Field(default_factory=RunFlowConfig)
    logging:              LoggingConfig            = Field(default_factory=LoggingConfig)
    skins:                SkinsConfig              = Field(default_factory=SkinsConfig)
    security:             SecurityConfig           = Field(default_factory=SecurityConfig)
    hooks:                HooksConfig              = Field(default_factory=HooksConfig)
    ssh:                  SSHConfig                = Field(default_factory=SSHConfig)
    context:              ContextConfig            = Field(default_factory=ContextConfig)
    conversation:         ConversationConfig       = Field(default_factory=ConversationConfig)
    observability:        ObservabilityConfig      = Field(default_factory=ObservabilityConfig)
    secrets:              SecretsConfig            = Field(default_factory=SecretsConfig)
    file_store:           FileStoreConfig          = Field(default_factory=FileStoreConfig)
    git_providers:        GitProvidersConfig       = Field(default_factory=GitProvidersConfig)
    integrations:         IntegrationsConfig       = Field(default_factory=IntegrationsConfig)
    parallel_executor:    ParallelExecutorConfig   = Field(default_factory=ParallelExecutorConfig)
    migrations:           MigrationsConfig         = Field(default_factory=MigrationsConfig)
    workspace_dir:        str                      = "workspace"
    max_steps:            int                      = 30
    token_budget:         int                      = 0
    auto_skill_threshold: int                      = 5
    redact_secrets:       bool                     = False

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def get(cls) -> "AppConfig":
        """Convenience: load config via the Config singleton."""
        return Config.get()._data


# ── v4.3.0: strict configuration placement validation ──────────────────────
#
# ROOT CAUSE this fixes (real test-run finding): ``max_steps = 80`` was
# written inside the TOML ``[logging]`` section. Pydantic's default
# ``extra='ignore'`` silently dropped the unknown key, so the runtime kept
# the default 30 while the user believed 80 was configured. A configuration
# section must never be able to SWALLOW an unrelated top-level setting.
#
# Mechanism: before pydantic validation, the raw (merged) config dict is
# walked against the real schema (derived from the pydantic models):
#
#   * a key that IS a valid TOP-LEVEL setting but sits inside a section
#     (e.g. ``[logging] max_steps``) → HARD ConfigError naming both the key
#       and the section, with the exact fix ("move it above any [section]")
#   * keys that are unknown anywhere → warning (collected, logged)
#   * ``SHSCODE_CONFIG_PERMISSIVE=1`` downgrades the hard error to a warning
#     (emergency escape hatch for legacy configs — documented, not default)


def _section_schemas() -> dict[str, set[str]]:
    """Section name → set of valid keys, derived from the pydantic models."""
    from pydantic import BaseModel
    out: dict[str, set[str]] = {}
    for fname, finfo in AppConfig.model_fields.items():
        candidates = [finfo.annotation]
        candidates += list(get_args(finfo.annotation))
        for cand in candidates:
            if isinstance(cand, type) and issubclass(cand, BaseModel):
                out[fname] = set(cand.model_fields.keys())
                break
    return out


def validate_config_placement(raw: dict) -> tuple[list[str], list[str]]:
    """Return (hard_errors, warnings) for misplaced config keys.

    A top-level setting found inside a section is a HARD error — that is
    exactly the ``[logging] max_steps`` bug class. Unknown keys are soft
    warnings so legacy configs keep loading.
    """
    top_fields = set(AppConfig.model_fields.keys())
    sections = _section_schemas()
    errors: list[str] = []
    warnings: list[str] = []
    for key, value in raw.items():
        if isinstance(value, dict):
            allowed = sections.get(key)
            if allowed is None:
                warnings.append(
                    f"unknown config section [{key}] (ignored — not in the schema)")
                continue
            for sub in value:
                if sub in top_fields and sub not in allowed:
                    errors.append(
                        f"'{sub}' is a TOP-LEVEL setting, but it was found inside "
                        f"the [{key}] section. It was silently IGNORED there. Move it "
                        f"to the top of the config file — above any [{key}] line — "
                        f"for it to take effect.")
                elif sub not in allowed:
                    warnings.append(
                        f"unknown key '{key}.{sub}' (ignored — not a [{key}] setting)")
        elif key not in top_fields:
            warnings.append(
                f"unknown top-level key '{key}' (ignored — not in the schema)")
    return errors, warnings


def _parse_max_steps(value) -> Optional[int]:
    """Parse + validate a max_steps value (int >= 1). None when unset/invalid."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def effective_max_steps() -> tuple[int, str]:
    """The max_steps the runtime must ACTUALLY use right now → (value, source).

    Resolution (highest first):
      1. ``SHSCODE_MAX_STEPS`` env var          — read FRESH every call, so
         runtime changes (CLI --max-steps, GUI run setting, /config/max-steps)
         apply to newly created agents without a config reload
      2. the loaded configuration value         — file layering already done
         (profile > home yaml > home toml > project config.toml)
      3. built-in default (30)

    The returned ``source`` describes where the value came from, so every
    surface (CLI /config, GUI Settings, run-start log) can SHOW the user
    which layer is in effect — the effective value can never silently
    disagree with what the user supplied again.
    """
    raw = env.getenv("MAX_STEPS", "")
    if raw:
        n = _parse_max_steps(raw)
        if n is not None:
            return n, "env SHSCODE_MAX_STEPS (runtime override)"
        _logger().warning(
            f"SHSCODE_MAX_STEPS={raw!r} is not a valid integer >= 1 — ignored")
    try:
        inst = Config.get()
        cfg = inst._data
    except Exception:
        return 30, "default"
    src = getattr(inst, "_max_steps_source", None) or "default (30)"
    return cfg.max_steps, src


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` ONTO ``base`` (overlay wins per-key)."""
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """
    Thread-safe singleton config loader with named profile support.
    """

    _instance: Optional["Config"] = None
    # v4.3.0: RLock — Config.get() is re-entrant now (loading can lazily
    # import modules whose import-time code calls Config.get() again; a
    # plain Lock deadlocked the whole process — found live).
    _lock: threading.RLock        = threading.RLock()

    def __init__(self, path: str = "config.toml") -> None:
        # v4.3.0 provenance: which layer supplied max_steps (file path / env)
        self._max_steps_file: Optional[str] = None
        self._max_steps_source: Optional[str] = None
        self._data: AppConfig = self._load(path)

    @classmethod
    def get(cls, path: str = "config.toml") -> "Config":
        # FIX: Thread-safety gap — the original checked _instance outside the lock
        # which could lead to a race condition where two threads both see None.
        # Double-checked locking pattern fixes this.
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Persistence (SHS Code) — write active config so changes survive restart
    # ------------------------------------------------------------------

    def active_config_path(self) -> Path:
        """Where /model, /provider, /mcp add etc. persist changes.
        Profile dir if SHSCODE_PROFILE set, else ~/.shscode/config.yaml
        (which takes precedence over ./config.toml on next load)."""
        profile = env.getenv("PROFILE", "").strip()
        if profile:
            pdir = _HOME / "profiles" / profile
            pdir.mkdir(parents=True, exist_ok=True)
            return pdir / "config.yaml"
        _HOME.mkdir(parents=True, exist_ok=True)
        return _HOME / "config.yaml"

    def save_llm(self, persist: bool = True) -> Optional[Path]:
        """Persist the current live LLM settings (provider/model/key/rate limit).
        Returns the written path or None on failure. Secrets are written with
        0600 perms; failures never raise into callers."""
        try:
            import yaml as __yaml
            target = self.active_config_path()
            data: dict = {}
            if target.exists():
                try:
                    data = __yaml.safe_load(target.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}
            llm = self._data.llm
            data.setdefault("llm", {})
            data["llm"].update({
                "provider": llm.provider,
                "model": llm.model,
                "base_url": llm.base_url,
                "api_key": llm.api_key,
                "max_tokens": llm.max_tokens,
                "temperature": llm.temperature,
                "timeout": llm.timeout,
                "max_retries": llm.max_retries,
                "rate_limit": {"enabled": llm.rate_limit.enabled, "rpm": llm.rate_limit.rpm},
            })
            if persist:
                tmp = target.with_suffix(".tmp")
                tmp.write_text(__yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, target)
            return target
        except Exception:
            return None

    def save_max_steps(self, value: Optional[int]) -> Optional[Path]:
        """v4.3.0: persist the user's default max_steps choice.

        ``value=None`` REMOVES the setting (back to file/default layers).
        Writes the active config file (0600, atomic replace) and mirrors the
        choice into the live process env so newly created agents pick it up
        immediately without a config reload. Failures never raise.
        """
        try:
            import yaml as __yaml
            if value is not None and (not isinstance(value, int) or value < 1):
                return None
            target = self.active_config_path()
            data: dict = {}
            if target.exists():
                try:
                    data = __yaml.safe_load(target.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}
            if value is None:
                data.pop("max_steps", None)
                os.environ.pop("SHSCODE_MAX_STEPS", None)
                os.environ.pop("MANUSCLAW_MAX_STEPS", None)
            else:
                data["max_steps"] = int(value)
                os.environ["SHSCODE_MAX_STEPS"] = str(int(value))
            tmp = target.with_suffix(".tmp")
            tmp.write_text(__yaml.safe_dump(data, allow_unicode=True),
                           encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, target)
            return target
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _load(self, path: str) -> AppConfig:
        self._load_dotenv_chain()
        raw = self._load_config_files(path)

        # v4.3.0: strict placement validation BEFORE pydantic — a top-level
        # setting inside a section is a hard, actionable error (this is the
        # [logging] max_steps bug class). Warnings are logged, never fatal.
        try:
            hard_errors, soft_warnings = validate_config_placement(raw)
        except Exception as e:  # never let the validator itself break loading
            _logger().warning(f"[Config] placement validation skipped: {e}")
            hard_errors, soft_warnings = [], []
        for w in soft_warnings:
            _logger().warning(f"[Config] {w}")
        if hard_errors:
            permissive = env.getenv("CONFIG_PERMISSIVE", "").lower() in ("1", "true", "yes")
            detail = "\n  ".join(hard_errors)
            if permissive:
                for e_ in hard_errors:
                    _logger().warning(f"[Config] (permissive) {e_}")
            else:
                raise ConfigError(
                    "Configuration placement error — settings were found in the "
                    "wrong section and would be silently ignored:\n  " + detail +
                    "\nFix the config file, or set SHSCODE_CONFIG_PERMISSIVE=1 to "
                    "downgrade this to a warning.")

        env_str = os.getenv("APP_ENV", raw.get("env", "dev")).lower()
        try:
            app_env = AppEnv(env_str)
        except ValueError:
            app_env = AppEnv.DEV

        try:
            cfg = AppConfig.model_validate(raw) if raw else AppConfig()
        except Exception as e:
            raise ConfigError(f"Config validation failed: {e}") from e

        cfg.env = app_env

        # Overlay environment variables
        if not cfg.llm.api_key:
            # FIX: Pick provider-specific env var first so that having both
            # OPENAI_API_KEY and ANTHROPIC_API_KEY doesn't incorrectly pick
            # OPENAI_API_KEY when provider="anthropic".
            _provider_key_map = {
                "openai":    os.getenv("OPENAI_API_KEY"),
                "anthropic": os.getenv("ANTHROPIC_API_KEY"),
                "mistral":   os.getenv("MISTRAL_API_KEY"),
                "google":    os.getenv("GOOGLE_API_KEY"),
                "gemini":    os.getenv("GOOGLE_API_KEY"),
            }
            cfg.llm.api_key = (
                _provider_key_map.get(cfg.llm.provider)
                or os.getenv("OPENAI_API_KEY")
                or os.getenv("ANTHROPIC_API_KEY")
                or os.getenv("MISTRAL_API_KEY")
                or os.getenv("LLM_API_KEY")
                # SHS Code FIX: NVIDIA NIM convention — a universal/NIM
                # endpoint configured via LLM_BASE_URL + NVIDIA_API_KEY
                # (no LLM_API_KEY) must also resolve its key.
                or os.getenv("NVIDIA_API_KEY")
            )
        if not cfg.llm.base_url:
            cfg.llm.base_url = os.getenv("LLM_BASE_URL")
        if cfg.llm.provider in ("mock", ""):
            detected = self._detect_provider()
            if detected:
                cfg.llm.provider = detected

        # Model override: CLI flag wins; standard LLM_MODEL env var also
        # honored so env-var-only setups (NIM/vLLM/Together via ~/.shscode/.env)
        # never fall back to the gpt-4o default against a non-OpenAI endpoint.
        model_override = os.getenv("LLM_MODEL_OVERRIDE", "") or os.getenv("LLM_MODEL", "")
        if model_override:
            cfg.llm.model = model_override

        # v3.0.3: env-var-only universal setups had NO model set -> default
        # 'gpt-4o' 404s on NVIDIA NIM / vLLM etc. If the model is still the
        # OpenAI default while a non-OpenAI universal endpoint is configured,
        # fail LOUDLY with instructions instead of a cryptic 404.
        if (
            cfg.llm.provider in ("universal", "openai-compat")
            and cfg.llm.model == "gpt-4o"
            and cfg.llm.base_url
            and "api.openai.com" not in (cfg.llm.base_url or "")
            and os.getenv("LLM_BASE_URL")
        ):
            import warnings
            warnings.warn(
                "LLM_BASE_URL is set to a non-OpenAI endpoint but no model is "
                "configured — the default 'gpt-4o' will 404. Set model in "
                "config.toml [llm] or export LLM_MODEL (e.g. "
                "LLM_MODEL=openai/gpt-oss-20b for NVIDIA NIM).",
                stacklevel=3,
            )

        # Test environment overrides — v4.3.0: max_steps is only forced to 5
        # when the user did NOT configure it explicitly (no file layer, still
        # the default 30). An explicit file/env value must survive the test
        # environment; silently replacing a user-supplied value is the bug
        # class this release fixes.
        if app_env == AppEnv.TEST:
            cfg.llm.provider = "mock"
            if cfg.max_steps == 30 and not self._max_steps_file:
                cfg.max_steps = 5
                # v4.3.0: the test-env speedup value is NOT a user choice —
                # label it as a default so mode scaling still applies and
                # nothing treats 5 as an explicitly configured budget.
                self._max_steps_source = "default (30; test env uses 5)"
            cfg.runflow.timeout = 60

        # Final fallback
        safe_providers = {"mock", "ollama", "lmstudio", "universal", "openai-compat", "gguf", "huggingface", "hf", ""}
        if cfg.llm.provider not in safe_providers and not cfg.llm.api_key and not cfg.llm.base_url:
            import warnings
            warnings.warn(
                f"LLM provider {cfg.llm.provider!r} needs API key. Falling back to MockLLM.",
                stacklevel=3,
            )
            cfg.llm.provider = "mock"

        cfg.redact_secrets = (
            cfg.logging.redact_secrets
            or env.getenv("REDACT", "").lower() in ("1", "true", "yes")
        )

        # ── Overlay env vars for new modules ──────────────────────────────
        if not cfg.security.cipher_key:
            cfg.security.cipher_key = env.getenv("CIPHER_KEY")
        if not cfg.git_providers.github_token:
            cfg.git_providers.github_token = os.getenv("GITHUB_TOKEN")
        if not cfg.git_providers.gitlab_token:
            cfg.git_providers.gitlab_token = os.getenv("GITLAB_TOKEN")
        if not cfg.git_providers.azure_devops_token:
            cfg.git_providers.azure_devops_token = os.getenv("AZURE_DEVOPS_TOKEN")
        if not cfg.git_providers.forgejo_token:
            cfg.git_providers.forgejo_token = os.getenv("FORGEJO_TOKEN")
        if not cfg.migrations.database_url:
            cfg.migrations.database_url = os.getenv("DATABASE_URL")
        if not cfg.file_store.s3_bucket:
            cfg.file_store.s3_bucket = os.getenv("S3_BUCKET")
        if not cfg.file_store.gcs_bucket:
            cfg.file_store.gcs_bucket = os.getenv("GCS_BUCKET")

        # ── v4.3.0: max_steps resolution + provenance ─────────────────────
        # Precedence: SHSCODE_MAX_STEPS env (explicit runtime choice — CLI
        # --max-steps, GUI run setting, /config/max-steps) > config files >
        # default. The value the runtime uses and SHOWS is always this one.
        env_ms = env.getenv("MAX_STEPS", "")
        if env_ms:
            n = _parse_max_steps(env_ms)
            if n is None:
                raise ConfigError(
                    f"SHSCODE_MAX_STEPS={env_ms!r} is invalid — use an integer >= 1")
            cfg.max_steps = n
            self._max_steps_source = "env SHSCODE_MAX_STEPS (explicit)"
        elif self._max_steps_source is None:
            if self._max_steps_file:
                self._max_steps_source = f"file {self._max_steps_file}"
            elif cfg.max_steps != 30:
                self._max_steps_source = "config"
            else:
                self._max_steps_source = "default (30)"
        logger = _logger()
        logger.info(
            f"[Config] max_steps={cfg.max_steps} "
            f"(source: {self._max_steps_source})")

        return cfg

    def _load_dotenv_chain(self) -> None:
        profile = env.getenv("PROFILE", "")
        candidates: list[Path] = []
        if profile:
            candidates.append(_HOME / "profiles" / profile / ".env")
        candidates.append(_HOME / ".env")
        candidates.append(Path(".env"))
        try:
            from dotenv import load_dotenv
            for p in reversed(candidates):
                if p.exists():
                    load_dotenv(p, override=False)
        except ImportError:
            pass

    def _load_config_files(self, legacy_path: str) -> dict:
        """Load and MERGE all config layers.

        SHS Code FIX (config shadowing): the old loader returned the FIRST
        existing file. A partial ``~/.shscode/config.yaml`` (e.g. written
        by the MCP manager containing only ``mcp_servers: []``) silently
        shadowed the ENTIRE project ``config.toml`` — the LLM provider
        quietly fell back to mock. Layers are now deep-merged, lowest
        priority first, so each layer only overrides the keys it defines:

            project config.toml  <  home config.toml  <  home config.yaml
                                                                    < profile
        """
        profile = env.getenv("PROFILE", "")
        candidates: list[Path] = []
        candidates.append(Path(legacy_path))          # lowest priority
        candidates.append(_HOME / "config.toml")
        candidates.append(_HOME / "config.yaml")      # home yaml wins over toml
        if profile:
            pd = _HOME / "profiles" / profile
            candidates.append(pd / "config.toml")
            candidates.append(pd / "config.yaml")     # highest priority

        merged: dict = {}
        for p in candidates:
            if not p.exists():
                continue
            try:
                data: dict = {}
                if p.suffix in (".yaml", ".yml") and _HAS_YAML:
                    with open(p) as f:
                        data = _yaml.safe_load(f) or {}
                elif p.suffix == ".toml" and tomllib is not None:
                    with open(p, "rb") as f:
                        data = tomllib.load(f)
                if isinstance(data, dict):
                    # v3.0.1: an EMPTY list in a higher layer means "no
                    # opinion", not "erase" — the MCP manager writes
                    # ``mcp_servers: []`` into the home yaml whenever
                    # nothing is configured interactively, which used to
                    # shadow project-level MCP servers entirely.
                    data = {
                        k: v for k, v in data.items()
                        if not (isinstance(v, list) and not v)
                    }
                    if data:
                        merged = _deep_merge(merged, data)
                        # v4.3.0 provenance: remember the highest-priority
                        # layer that defines top-level max_steps (later
                        # layers win the merge, so the LAST writer is the
                        # effective one). Shows the user where the value
                        # came from (transparency requirement).
                        if "max_steps" in data:
                            self._max_steps_file = str(p)
            except Exception as e:
                raise ConfigError(f"Failed to parse {p}: {e}") from e
        return merged

    @staticmethod
    def _detect_provider() -> Optional[str]:
        if os.getenv("OPENAI_API_KEY"):    return "openai"
        if os.getenv("ANTHROPIC_API_KEY"): return "anthropic"
        if os.getenv("MISTRAL_API_KEY"):   return "mistral"
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            return "bedrock"
        if os.getenv("GOOGLE_API_KEY"):    return "google"
        # SHS Code FIX (any-directory universal — found in live NIM E2E):
        # an explicit LLM_BASE_URL defines an OpenAI-compatible endpoint
        # (NVIDIA NIM, vLLM, Together, Groq, ...). Previously this returned
        # None -> provider stayed "mock" -> SILENT MockLLM fallback whenever
        # the agent ran outside a directory containing a project config.toml.
        # Env-based universal configuration (LLM_BASE_URL + LLM_API_KEY or
        # NVIDIA_API_KEY) must work in ANY cwd, not only inside the repo.
        if os.getenv("LLM_BASE_URL"):
            return "universal"
        return None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def env(self) -> AppEnv:              return self._data.env
    @property
    def llm(self) -> LLMConfig:           return self._data.llm
    @property
    def browser(self) -> BrowserConfig:   return self._data.browser
    @property
    def search(self) -> SearchConfig:     return self._data.search
    @property
    def sandbox(self) -> SandboxConfig:   return self._data.sandbox
    @property
    def mcp_servers(self) -> list[MCPServerDef]: return self._data.mcp_servers
    @property
    def runflow(self) -> RunFlowConfig:   return self._data.runflow
    @property
    def logging(self) -> LoggingConfig:   return self._data.logging
    @property
    def skins(self) -> SkinsConfig:              return self._data.skins
    @property
    def security(self) -> SecurityConfig:         return self._data.security
    @property
    def hooks(self) -> HooksConfig:                return self._data.hooks
    @property
    def ssh(self) -> "SSHConfig":                   return self._data.ssh
    @property
    def context(self) -> ContextConfig:            return self._data.context
    @property
    def conversation(self) -> ConversationConfig:  return self._data.conversation
    @property
    def observability(self) -> ObservabilityConfig: return self._data.observability
    @property
    def secrets(self) -> SecretsConfig:            return self._data.secrets
    @property
    def file_store(self) -> FileStoreConfig:       return self._data.file_store
    @property
    def git_providers(self) -> GitProvidersConfig: return self._data.git_providers
    @property
    def integrations(self) -> IntegrationsConfig:  return self._data.integrations
    @property
    def parallel_executor(self) -> ParallelExecutorConfig: return self._data.parallel_executor
    @property
    def migrations(self) -> MigrationsConfig:      return self._data.migrations
    @property
    def workspace_dir(self) -> str:                return self._data.workspace_dir
    @property
    def max_steps(self) -> int:           return self._data.max_steps
    @property
    def max_steps_source(self) -> str:
        """v4.3.0: provenance of the effective max_steps (for /config, GUI)."""
        return self._max_steps_source or "default (30)"
    @property
    def token_budget(self) -> int:        return self._data.token_budget
    @property
    def auto_skill_threshold(self) -> int: return self._data.auto_skill_threshold
    @property
    def redact_secrets(self) -> bool:     return self._data.redact_secrets

    def is_prod(self) -> bool:  return self._data.env == AppEnv.PROD
    def is_dev(self) -> bool:   return self._data.env == AppEnv.DEV
    def is_test(self) -> bool:  return self._data.env == AppEnv.TEST
