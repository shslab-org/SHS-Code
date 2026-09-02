from __future__ import annotations

"""
Delegate tool — spawns an isolated subagent.

SHS Code Phase 2 (spec §26): every spawned subagent has PERSISTENT
identity — start/finish (or interruption) is recorded in journal.db
(subagents table) with role, goal, output, files changed and error.
A parent agent (or /resume) can recover subagent progress after a
crash: incomplete subagents are listed with their original goals.
"""
import asyncio
from app.tool.base import BaseTool
from app.schema import ToolResult


class DelegateTool(BaseTool):
    name = "delegate"
    description = (
        "Spawn an isolated subagent to handle an independent subtask. "
        "Use for tasks that can run in parallel or need full isolation. "
        "Subagent progress is persisted (survives crashes/interruption)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The subtask description"},
            "role": {"type": "string",
                     "description": "subagent role label (coder, researcher, tester, reviewer...)"},
            "max_steps": {"type": "integer", "default": 15},
            "timeout": {"type": "integer", "default": 300},
        },
        "required": ["task"],
    }

    def __init__(self, task_provider=None) -> None:
        # task_provider: callable returning (journal, task_id) of the parent run
        self._task_provider = task_provider

    async def execute(self, task: str, role: str = "worker",
                      max_steps: int = 15, timeout: int = 300) -> ToolResult:
        from app.agent.manus import Manus
        from app.permissions.gate import AgentMode

        journal, parent_task_id = (self._task_provider() if self._task_provider
                                   else (None, None))
        sub_id = ""
        if journal and parent_task_id:
            try:
                from app.subagents import start_subagent, finish_subagent
                sub_id = await start_subagent(journal, parent_task_id, task,
                                              role=role or "worker")
            except Exception:
                sub_id = ""

        async def _run() -> str:
            agent = Manus(mode=AgentMode.BUILD)
            agent._max_steps = max_steps
            return await agent.run(task)

        try:
            result = await asyncio.wait_for(_run(), timeout=timeout)
            if journal and parent_task_id and sub_id:
                try:
                    await finish_subagent(journal, parent_task_id, sub_id,
                                          output=result)
                except Exception:
                    pass
            return ToolResult(output=f"[Delegate {role or 'worker'} {sub_id} completed]\n{result[:3000]}")
        except asyncio.TimeoutError as e:
            if journal and parent_task_id and sub_id:
                try:
                    await finish_subagent(journal, parent_task_id, sub_id,
                                          error=f"timed out after {timeout}s")
                except Exception:
                    pass
            return ToolResult(error=f"Subagent timed out after {timeout}s")
        except Exception as e:
            if journal and parent_task_id and sub_id:
                try:
                    await finish_subagent(journal, parent_task_id, sub_id,
                                          error=str(e))
                except Exception:
                    pass
            return ToolResult(error=f"Subagent error: {e}")
