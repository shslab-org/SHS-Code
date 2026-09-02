from __future__ import annotations

"""
SHS Code — project_intel tool
===============================
Project-level intelligence for the agent (spec §2/§28/§29):
  summary      — project profile (type, languages, frameworks, commands)
  architecture — symbol-weight map + import hubs
  entry        — entry points + important files
  env          — development environment (tools, runtimes, versions)
  refresh      — force incremental reindex
  git          — full git intelligence snapshot (branch, diff, conflicts)

All output comes from real inspection — never from documentation claims.
"""

from typing import Any

from app.schema import ToolResult
from app.tool.base import BaseTool

_ACTIONS = ("summary", "architecture", "entry", "env", "refresh", "git")


class ProjectIntelTool(BaseTool):
    name = "project_intel"
    description = (
        "Inspect project-level intelligence: 'summary' (project type, languages, "
        "frameworks, build/test/run commands), 'architecture' (symbol weight by "
        "directory + most-imported modules), 'entry' (entry points + important "
        "files), 'env' (available tools/runtimes with versions), 'git' (branch, "
        "dirty files, conflicts, recent commits), 'refresh' (incremental reindex)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(_ACTIONS),
                       "description": "what to inspect (default: summary)"},
        },
    }

    async def execute(self, action: str = "summary", **_: Any) -> ToolResult:
        action = (action or "summary").lower().strip()
        if action not in _ACTIONS:
            return ToolResult(error=f"unknown action '{action}'. Use: {', '.join(_ACTIONS)}")
        try:
            if action == "summary":
                from app.intelligence import current_intelligence
                intel = current_intelligence()
                intel.ensure_indexed()
                return ToolResult(output=intel.summary())

            if action == "architecture":
                from app.intelligence import current_intelligence
                intel = current_intelligence()
                intel.ensure_indexed()
                return ToolResult(output=intel.architecture_map())

            if action == "entry":
                from app.intelligence import current_intelligence
                from app.intelligence.project import IMPORTANT_FILES
                from pathlib import Path
                intel = current_intelligence()
                p = intel.profile()
                lines = ["ENTRY POINTS: " + (", ".join(p.get("entry_points") or [])
                                              or "(none detected)")]
                lines.append("IMPORTANT FILES: " + ", ".join(
                    f for f in p.get("important_files") or []))
                lines.append("TEST FRAMEWORKS: " + ", ".join(
                    p.get("test_frameworks") or []))
                lines.append("COMMANDS:")
                for k, v in (p.get("commands") or {}).items():
                    lines.append(f"  {k}: {'; '.join(v)}")
                return ToolResult(output="\n".join(lines))

            if action == "env":
                from app.intelligence.environment import environment_summary, command_available
                out = environment_summary()
                return ToolResult(output=out + "\n(check a specific command exists"
                                            " before running it)")

            if action == "git":
                from app.git_intel import GitIntelligence
                return ToolResult(output=GitIntelligence().render())

            if action == "refresh":
                from app.intelligence import current_intelligence
                from app.activity import emit
                intel = current_intelligence()
                emit("indexing", project=intel.root.name)
                stats = intel.ensure_indexed(force=True)
                return ToolResult(output=(
                    f"Index refreshed: {stats.get('files', 0)} files, "
                    f"{stats.get('symbols', 0)} symbols, "
                    f"{stats.get('changed', 0)} changed, "
                    f"{stats.get('ms', 0)}ms (incremental — only changed files reindexed)"))
        except Exception as e:
            return ToolResult(error=f"project_intel failed: {e}")
        return ToolResult(error="unreachable")
