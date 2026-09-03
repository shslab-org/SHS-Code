"""SHS Code environment variable resolution.

Canonical environment prefix: ``SHSCODE_*``

Legacy fallback: ``MANUSCLAW_*`` variables (and the legacy
``~/.shscode`` home directory) are consulted ONLY when the canonical
name is unset, so that installations created before the SHS Code rename
keep their configuration and persisted state. This module is the single
compatibility point for the rename; no other code should reference the
legacy prefix.
"""

from __future__ import annotations

import os
from pathlib import Path

_CANONICAL_PREFIX = "SHSCODE_"
_LEGACY_PREFIX = "MANUSCLAW_"

_LEGACY_HOME = Path.home() / ".manusclaw"
_CANONICAL_HOME = Path.home() / ".shscode"


def _normalize_environ() -> None:
    """Map legacy ``MANUSCLAW_*`` env vars onto canonical ``SHSCODE_*`` names.

    Runs once at import: for every legacy variable that is set while the
    canonical one is not, the canonical name is defined with the same value.
    This keeps pre-rename installations (shell profiles, ``.env`` files)
    working without any user action.
    """
    for key in list(os.environ.keys()):
        if key.startswith(_LEGACY_PREFIX):
            canonical = _CANONICAL_PREFIX + key[len(_LEGACY_PREFIX):]
            if canonical not in os.environ:
                os.environ[canonical] = os.environ[key]


_normalize_environ()


def getenv(name: str, default: str | None = None) -> str | None:
    """Read an SHS Code environment variable.

    Resolution order:
      1. ``SHSCODE_<name>`` (canonical)
      2. ``MANUSCLAW_<name>`` (legacy fallback, pre-rename installations)
      3. ``default``

    ``name`` is the suffix without the prefix, e.g. ``getenv("HOME")``
    reads ``SHSCODE_HOME`` then ``MANUSCLAW_HOME``.
    """
    value = os.getenv(_CANONICAL_PREFIX + name)
    if value is not None:
        return value
    value = os.getenv(_LEGACY_PREFIX + name)
    if value is not None:
        return value
    return default


def home_dir() -> Path:
    """Resolve the SHS Code home directory.

    Order:
      1. ``SHSCODE_HOME`` / legacy ``MANUSCLAW_HOME`` env var
      2. ``~/.shscode`` if it exists (canonical location)
      3. ``~/.shscode`` if it exists (legacy data — state preserved)
      4. ``~/.shscode`` (fresh install default)
    """
    override = getenv("HOME")
    if override:
        return Path(override).expanduser()
    if _CANONICAL_HOME.exists():
        return _CANONICAL_HOME
    if _LEGACY_HOME.exists():
        return _LEGACY_HOME
    return _CANONICAL_HOME


def workspace_dir() -> Path:
    """Resolve the workspace directory (``SHSCODE_WORKSPACE`` or ``workspace``)."""
    return Path(getenv("WORKSPACE", "workspace"))


def prefix() -> str:
    """Canonical env prefix (for diagnostics/help text)."""
    return _CANONICAL_PREFIX
