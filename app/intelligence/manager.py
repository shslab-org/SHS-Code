from __future__ import annotations

"""
SHS Code — Project Intelligence Manager (facade, spec §2-§4)
==============================================================
Ties together: incremental index cache + project profile + semantic search.

Per-project singletons (LRU bounded). The profile is persisted at
~/.manusclaw/intel/<hash>/profile.json and refreshed when stale (>10 min)
or on explicit demand (force=True).

Async surface (used by agent tools / CLI):
  await get_intelligence(root)      -> Intelligence handle
  await intel.refresh()             -> incremental index update
  await intel.profile()             -> project profile dict
  await intel.summary()             -> compact LLM-readable summary
  await intel.search(mode, query)   -> search_dispatch
  intel.on_files_changed(paths)     -> cheap partial reindex after edits

Sync surface is also available for tests and the doctor.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.intelligence.cache import IntelligenceCache
from app.intelligence.project import build_profile, summarize_profile
from app.intelligence.search import search_dispatch, format_search_results
from app.logger import logger

PROFILE_STALE_S = 600  # 10 min

_instances: Dict[str, "Intelligence"] = {}
_lock = asyncio.Lock() if False else None  # (threading lock used instead)
import threading
_tlock = threading.RLock()


class Intelligence:
    """Per-project intelligence handle."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.cache = IntelligenceCache(self.root)
        self.profile_path = self.cache.dir / "profile.json"
        self._profile: Optional[Dict[str, Any]] = None
        self._profile_at: float = 0.0
        self._refreshed = False

    # -- sync API -----------------------------------------------------------

    def _load_profile(self, force: bool = False) -> Dict[str, Any]:
        stale = (time.time() - self._profile_at) > PROFILE_STALE_S
        if self._profile is not None and not force and not stale:
            return self._profile
        if self.profile_path.exists() and not force:
            try:
                data = json.loads(self.profile_path.read_text(encoding="utf-8"))
                if data.get("file_stats") and time.time() - data.get("built_at", 0) < PROFILE_STALE_S:
                    self._profile, self._profile_at = data, time.time()
                    return data
            except Exception as e:
                logger.debug(f"[Intel] profile load failed: {e}")
        lang_stats = self.cache.language_stats()
        fstats = self.cache.file_stats()
        profile = build_profile(self.root, language_stats=lang_stats, file_stats=fstats)
        profile["built_at"] = time.time()
        try:
            self.profile_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            logger.debug(f"[Intel] profile save failed: {e}")
        self._profile, self._profile_at = profile, time.time()
        return profile

    def ensure_indexed(self, force: bool = False) -> Dict[str, int]:
        """Index on first use; later calls are cheap incremental refreshes."""
        if self._refreshed and not force:
            return self.cache.file_stats()  # type: ignore[return-value]
        stats = self.cache.refresh(force=force)
        self._refreshed = True
        return stats

    def on_files_changed(self, rel_paths: List[str]) -> int:
        """Cheap partial reindex after agent edits (spec §3 incremental)."""
        n = self.cache.refresh_paths(rel_paths)
        self._profile = None  # profile is stale now
        return n

    def profile(self, force: bool = False) -> Dict[str, Any]:
        self.ensure_indexed()
        return self._load_profile(force=force)

    def summary(self) -> str:
        return summarize_profile(self.profile())

    def search(self, mode: str, query: str, limit: int = 20) -> Dict[str, Any]:
        self.ensure_indexed()
        return search_dispatch(self.cache, mode, query, limit)

    def architecture_map(self) -> str:
        """Directory-weight + dependency-hub map (spec §2 architecture)."""
        self.ensure_indexed()
        dirs = self.cache.source_dir_stats()
        hubs = self.cache.modules_imported_most(limit=12)
        lines = ["ARCHITECTURE (symbol weight by directory):"]
        for d in dirs[:15]:
            lines.append(f"  {d.get('top') or '.':<28} {d['n']:>6} symbols")
        lines.append("\nIMPORT HUBS (most-imported modules):")
        for h in hubs:
            if h["n"] >= 2:
                lines.append(f"  {h['module']:<48} imported x{h['n']}")
        return "\n".join(lines)

    # -- async API (agent-facing) -------------------------------------------

    async def a_refresh(self, force: bool = False) -> Dict[str, int]:
        return await asyncio.to_thread(self.ensure_indexed, force)

    async def a_profile(self, force: bool = False) -> Dict[str, Any]:
        return await asyncio.to_thread(self.profile, force)

    async def a_summary(self) -> str:
        return await asyncio.to_thread(self.summary)

    async def a_search(self, mode: str, query: str, limit: int = 20) -> str:
        res = await asyncio.to_thread(self.search, mode, query, limit)
        return format_search_results(res)

    async def a_architecture(self) -> str:
        return await asyncio.to_thread(self.architecture_map)

    async def a_files_changed(self, rel_paths: List[str]) -> int:
        return await asyncio.to_thread(self.on_files_changed, rel_paths)


def get_intelligence(root: Optional[Path] = None) -> Intelligence:
    """Get (creating if needed) the Intelligence handle for a project root."""
    root = Path(root or Path.cwd()).resolve()
    key = str(root)
    with _tlock:
        if key not in _instances:
            if len(_instances) >= 8:
                # LRU: drop oldest
                oldest = next(iter(_instances))
                _instances.pop(oldest, None)
            _instances[key] = Intelligence(root)
        return _instances[key]


def current_intelligence() -> Intelligence:
    return get_intelligence(Path.cwd())


# activity wiring — indexing emits a user-visible line (spec §58)
_orig_refresh = Intelligence.ensure_indexed


def _instrumented_refresh(self: Intelligence, force: bool = False):
    from app.activity import emit
    emit("indexing", project=self.root.name)
    stats = _orig_refresh(self, force=force)
    emit("indexed", files=stats.get("files", 0),
         symbols=stats.get("symbols", 0), ms=stats.get("ms", 0))
    return stats


Intelligence.ensure_indexed = _instrumented_refresh  # type: ignore[method-assign]
