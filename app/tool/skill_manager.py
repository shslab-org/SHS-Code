from __future__ import annotations
"""Skill manager tool — create, patch, delete, list, load skills."""
import re
from app.tool.base import BaseTool
from app.schema import ToolResult


def _word_overlap(a: str, b: str) -> float:
    """Fraction of significant words of `a` that appear in `b`."""
    words = [w for w in re.findall(r"[a-z]{3,}", (a or "").lower())]
    if not words:
        return 0.0
    b_lower = (b or "").lower()
    hits = sum(1 for w in words if w in b_lower)
    return hits / len(words)


class SkillManagerTool(BaseTool):
    name = "skill_manager"
    description = (
        "Manage procedural skills (reusable knowledge stored as Markdown). "
        "Actions: list, get, create, patch, delete. Skills are for REUSABLE "
        "workflows only — do NOT create a skill for the current one-off task."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "get", "create", "patch", "delete"]},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "content": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "version": {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, action: str, name: str = "", description: str = "",
                      content: str = "", tags=None, version: str = "1.0.0") -> ToolResult:
        from app.skills.skill_engine import get_skill_engine
        engine = get_skill_engine()
        try:
            if action == "list":
                skills = engine.list_skills()
                if not skills:
                    return ToolResult(output="No skills. Use create to add one.")
                lines = [f"Skills ({len(skills)}):"]
                for s in skills:
                    lines.append(f"  {s.name} v{s.version}: {s.description[:60]}")
                return ToolResult(output="\n".join(lines))
            elif action == "get":
                skill = engine.get(name)
                if skill is None:
                    skill = engine.get_skill(name)
                if not skill:
                    return ToolResult(error=f"Skill not found: {name}")
                return ToolResult(output=skill.to_file_content())
            elif action == "create":
                if not name or not content:
                    return ToolResult(error="name and content required")
                # v3.0.3 anti-noise guard (live finding): models were saving
                # a "skill" for every one-off task (file_creator,
                # calculator_project_setup, weather_query, …) — pure clutter.
                # A skill whose name+description substantially overlaps the
                # CURRENT goal is task-specific, not reusable: reject it and
                # tell the model to just finish the task.
                goal = self._current_goal()
                if goal:
                    sig = f"{name} {description}"
                    overlap = _word_overlap(sig, goal)
                    if overlap >= 0.5:
                        return ToolResult(output=(
                            f"SKILL CREATION SKIPPED: '{name}' overlaps the current "
                            f"task ({overlap:.0%} of its words come from the task "
                            "goal), so it is a one-off procedure, not a reusable "
                            "skill. Continue with the task itself — do not create "
                            "skills unless the user asks for a reusable workflow."
                        ))
                skill = engine.create(name, description, content, tags, version)
                return ToolResult(output=f"Skill created: {name} at {skill.path}")
            elif action == "patch":
                skill = engine.patch(name, content or None, description or None, version or None)
                if not skill:
                    return ToolResult(error=f"Not found: {name}")
                return ToolResult(output=f"Patched: {name} v{skill.version}")
            elif action == "delete":
                ok = engine.delete(name)
                return ToolResult(output=f"Deleted: {name}") if ok else ToolResult(error=f"Not found: {name}")
        except Exception as e:
            return ToolResult(error=str(e))

    def _current_goal(self) -> str:
        """Best-effort current task goal from the agent context, if any."""
        try:
            from app.agent.context import get_current_goal
            return get_current_goal()
        except Exception:
            return ""
