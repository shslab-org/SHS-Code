from __future__ import annotations

"""
SHS Code — code_search tool (Project Intelligence Layer for the LLM)
=====================================================================
Gives the agent semantic/structural code search over the indexed project
(spec §4): symbol search, text/regex, filename, import graphs, usages,
concept-level semantic search ("where is authentication handled").

Backed by the persistent incremental index — fast on large repos,
no repeated full scans.
"""

from typing import Any

from app.schema import ToolResult
from app.tool.base import BaseTool

_MODES = ("semantic", "symbol", "text", "regex", "filename", "import",
          "usages", "callers")


class CodeSearchTool(BaseTool):
    name = "code_search"
    description = (
        "Search the project's persistent code index. Modes: "
        "'semantic' (concept search, e.g. 'where is authentication handled' "
        "— expands to related symbols and ranks files), "
        "'symbol' (find class/function/method by name, optional kind prefix "
        "like 'class Journal'), 'text' (substring), 'regex' (line regex), "
        "'filename' (find files by name), 'import' (who imports module X), "
        "'usages' (where is symbol S referenced), "
        "'callers' (files importing from a given file). "
        "Always prefer this over bash grep — it uses the incremental index."
    )
    parameters = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": list(_MODES),
                     "description": "search mode (default: semantic)"},
            "query": {"type": "string",
                      "description": "search query (symbol name, pattern, concept, or file path)"},
            "limit": {"type": "integer", "description": "max results (default 15)"},
        },
        "required": ["query"],
    }

    async def execute(self, query: str = "", mode: str = "semantic",
                      limit: int = 15, **_: Any) -> ToolResult:
        if not query:
            return ToolResult(error="query is required")
        mode = (mode or "semantic").lower().strip()
        if mode not in _MODES:
            return ToolResult(error=f"unknown mode '{mode}'. Use one of: {', '.join(_MODES)}")
        try:
            from app.intelligence import current_intelligence
            from app.intelligence.search import format_search_results
            intel = current_intelligence()
            intel.ensure_indexed()
            res = intel.search(mode, query, limit=max(1, min(int(limit), 50)))
            out = format_search_results(res)
            if not (res.get("results") or res.get("symbols")):
                out += "\n(no matches — try another mode or broaden the query)"
            return ToolResult(output=out)
        except Exception as e:
            return ToolResult(error=f"code_search failed: {e}")
