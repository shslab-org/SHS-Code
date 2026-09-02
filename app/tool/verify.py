from __future__ import annotations

"""
SHS Code — verify tool (Verification Engine for the LLM, spec §15)
====================================================================
Runs project-aware verification: build / test / lint / typecheck /
validate — ONLY the checks that match the detected project type.

Implements the loop discipline of spec §5/§15: after implementation,
the agent MUST call this before claiming completion. Output includes
actionable failure analysis (error lines + hypotheses + fixes).

Usage by the agent is enforced socially via system prompts AND
structurally: /status shows the last verification verdict, and the
journal records it (record_verification).
"""

from typing import Any, List, Optional

from app.schema import ToolResult
from app.tool.base import BaseTool

_KINDS = ("build", "test", "lint", "typecheck", "validate", "syntax")


class VerifyTool(BaseTool):
    name = "verify"
    description = (
        "Run project-aware verification (spec: never claim done without it). "
        "Selects the RIGHT commands for the detected project: python → "
        "compileall + pytest; node → tsc/npm test; android → gradlew; etc. "
        "kinds: build|test|lint|typecheck|validate|syntax (default: project-"
        "appropriate set). Returns pass/fail per command with extracted "
        "errors, hypotheses and suggested fixes. level: fast|standard|thorough."
    )
    parameters = {
        "type": "object",
        "properties": {
            "kinds": {
                "type": "array", "items": {"type": "string", "enum": list(_KINDS)},
                "description": "verification kinds to run (default: auto-select)",
            },
            "level": {"type": "string", "enum": ["fast", "standard", "thorough"],
                      "description": "verification depth (default standard)"},
            "timeout_s": {"type": "integer",
                          "description": "per-command timeout seconds (default 420)"},
        },
    }

    def __init__(self, journal_task_provider=None, level_provider=None) -> None:
        # journal_task_provider: callable returning (journal, task_id)
        # level_provider: callable returning effective verification level (mode/profile-aware)
        self._task_provider = journal_task_provider
        self._level_provider = level_provider

    async def execute(self, kinds: Optional[List[str]] = None,
                      level: str = "", timeout_s: int = 420,
                      **_: Any) -> ToolResult:
        if not level and self._level_provider:
            try:
                level = self._level_provider() or "standard"
            except Exception:
                level = "standard"
        level = level or "standard"
        try:
            from app.verification import VerificationEngine, format_verification
            from app.activity import emit
            ve = VerificationEngine()
            emit("verifying", label=str(kinds or "auto"), level=level)
            report = await ve.verify(kinds=kinds, level=level, timeout=timeout_s)
            analysis = ve.analyze_failure(report)

            out = format_verification(report)
            if not report.get("ok"):
                out += "\n\nFAILURE ANALYSIS (spec §16 — diagnose before retrying):"
                for h in analysis.get("hypotheses", [])[:8]:
                    out += f"\n  • {h.get('class')}: {h.get('evidence', '')[:140]}"
                    out += f"\n      hypothesis: {h.get('hypothesis', '')}"
                    out += f"\n      fix: {h.get('fix', '')}"
                acts = analysis.get("suggested_actions") or []
                if acts:
                    out += "\nSUGGESTED ACTIONS:\n  - " + "\n  - ".join(acts[:6])
                out += ("\nDO NOT claim the task is complete. Fix the failures, "
                        "then run verify again.")
            else:
                out += ("\nAll selected verification passed — you may complete "
                        "the task IF the user's goal itself is met.")

            # journal the verification outcome (Work State 2.0, spec §9)
            try:
                if self._task_provider:
                    journal, task_id = self._task_provider()
                    if journal and task_id:
                        await journal.record_verification(task_id, {
                            "kind": "verify_tool",
                            "ok": report.get("ok"),
                            "summary": report.get("summary", "")[:300],
                            "kinds": report.get("kinds"),
                        })
                        for r in report.get("results", []):
                            await journal.record_test_result(
                                task_id, name=r.get("label", "verify"),
                                passed=bool(r.get("ok")),
                                detail=(r.get("output") or "")[:200])
            except Exception:
                pass
            return ToolResult(output=out)
        except Exception as e:
            return ToolResult(error=f"verify failed: {e}")
