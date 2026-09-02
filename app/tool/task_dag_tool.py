from __future__ import annotations

"""
SHS Code — task_dag tool (plan management for the LLM, spec §6-§8)
=====================================================================
Lets the agent drive the dependency-aware task graph:
  show      — render current plan + progress + next node
  add       — add a step (title, depends_on node ids, priority)
  start     — mark node active (begins work)
  complete  — mark node completed (REFUSED if dependencies incomplete)
  fail      — mark node retryable/failed with error
  skip      — skip with reason
  next      — the prioritized next node (dep unlock > priority > failures)

Everything persists to journal.db → survives restarts and model switches.
Dependency rule is enforced structurally: complete() is refused when
dependencies are not completed (spec §6).
"""

from typing import Any, List, Optional

from app.schema import ToolResult
from app.tool.base import BaseTool


class TaskDagTool(BaseTool):
    name = "task_dag"
    description = (
        "Manage the persisted dependency-aware plan (task graph). Actions: "
        "'show' (render plan+progress+next), 'add' (new step: title, optional "
        "depends_on=[node_id,...], priority 1-7), 'start' <node_id>, "
        "'complete' <node_id> (refused until dependencies completed), "
        "'fail' <node_id> <error> (retryable=true|false), 'skip' <node_id> "
        "<reason>, 'next' (prioritized next step). The graph persists across "
        "restarts and model switches — always keep it current."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["show", "add", "start", "complete", "fail",
                                "skip", "next"],
                       "description": "plan action (default: show)"},
            "node_id": {"type": "string", "description": "target node id"},
            "title": {"type": "string", "description": "step title (for add)"},
            "depends_on": {"type": "array", "items": {"type": "string"},
                           "description": "node ids this step depends on"},
            "priority": {"type": "integer", "minimum": 1, "maximum": 7,
                         "description": "1=critical .. 7=lowest (default 5)"},
            "error": {"type": "string", "description": "failure detail (for fail)"},
            "reason": {"type": "string", "description": "skip reason"},
            "retryable": {"type": "boolean", "description": "default true"},
        },
    }

    def __init__(self, task_provider=None) -> None:
        # task_provider: callable returning (journal, task_id) for the live run
        self._task_provider = task_provider

    async def execute(self, action: str = "show", node_id: str = "",
                      title: str = "", depends_on: Optional[List[str]] = None,
                      priority: int = 5, error: str = "", reason: str = "",
                      retryable: bool = True, **_: Any) -> ToolResult:
        journal, task_id = (self._task_provider() if self._task_provider
                            else (None, None))
        if journal is None or not task_id:
            return ToolResult(error=(
                "No active journaled task — the plan graph only exists "
                "inside an agent run. (This should not happen; report it.)"))
        try:
            from app.task_dag import TaskGraph
            g = await TaskGraph(journal, task_id).load()
            if action == "show":
                if not g.nodes():
                    return ToolResult(output="(plan is empty — add steps)")
                return ToolResult(output=g.render())
            if action == "next":
                n = g.next_node()
                return ToolResult(output=(
                    f"NEXT: {n.node_id} {n.title} (priority {n.priority})"
                    if n else "no actionable node — all done or blocked"))
            if action == "add":
                if not title:
                    return ToolResult(error="title required for add")
                node = await g.add_node(title, depends_on=depends_on,
                                        priority=int(priority))
                await g.sync_to_task()
                return ToolResult(output=(
                    f"added {node.node_id}: {node.title} (depends_on="
                    f"{node.depends_on})\n{g.render()}"))
            if action in ("start", "complete", "fail", "skip"):
                if not node_id:
                    return ToolResult(error=f"node_id required for {action}")
                if action == "start":
                    ok, msg = await g.start_node(node_id)
                elif action == "complete":
                    ok, msg = await g.complete_node(node_id)
                elif action == "fail":
                    ok, msg = await g.fail_node(node_id, error or "failed",
                                                retryable=retryable)
                else:
                    ok, msg = await g.skip_node(node_id, reason or "")
                await g.sync_to_task()
                if not ok:
                    return ToolResult(error=msg)
                return ToolResult(output=msg + "\n" + g.render())
            return ToolResult(error=f"unknown action '{action}'")
        except Exception as e:
            return ToolResult(error=f"task_dag failed: {e}")
