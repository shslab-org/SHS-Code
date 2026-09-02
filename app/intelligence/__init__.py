from __future__ import annotations

"""SHS Code — Project Intelligence Layer (Phase 2, spec §2-§4)."""

from app.intelligence.indexer import (
    LANGUAGE_BY_EXT, Symbol, ImportStmt, FileIndex,
    index_file, walk_source_files, should_skip_path, read_source,
)
from app.intelligence.cache import IntelligenceCache, project_cache_dir, INTEL_ROOT
from app.intelligence.project import build_profile, summarize_profile, git_state
from app.intelligence.environment import (
    detect_environment, environment_summary, has_tool, tool_path,
    command_available,
)
from app.intelligence.search import (
    SemanticSearch, search_dispatch, format_search_results, expand_query,
)
from app.intelligence.manager import (
    Intelligence, get_intelligence, current_intelligence,
)

__all__ = [
    "LANGUAGE_BY_EXT", "Symbol", "ImportStmt", "FileIndex",
    "index_file", "walk_source_files", "should_skip_path", "read_source",
    "IntelligenceCache", "project_cache_dir", "INTEL_ROOT",
    "build_profile", "summarize_profile", "git_state",
    "detect_environment", "environment_summary", "has_tool", "tool_path",
    "command_available",
    "SemanticSearch", "search_dispatch", "format_search_results", "expand_query",
    "Intelligence", "get_intelligence", "current_intelligence",
]
