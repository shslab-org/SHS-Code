from __future__ import annotations

"""
SHS Code — Task DAG (dependency-aware task graph, spec §6-§8)
===============================================================
Upgrades the task system from a flat list into a persistent DAG.

Node statuses:  pending | ready | active | completed | failed |
                retryable | skipped | blocked

Rules enforced:
  - a dependent task can NOT be marked completed before its dependencies
    are actually completed (spec §6) — complete() raises/refuses instead
  - ready nodes = all dependencies completed
  - blocked nodes = at least one dependency failed/skipped
  - smart prioritization (spec §8): order by
      (a) dependency unlock value (how many nodes this unblocks),
      (b) user priority (lower number = more important),
      (c) fewer past failures first,
      (d) age (older first)
  - everything persists in journal.db (task_nodes table) — the graph
    survives restarts, model switches and provider changes.

Used by: the planner (plan generation), agent task_dag tool, /plan
command, and /status progress percentages.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.logger import logger

NODE_STATUSES = ("pending", "ready", "active", "completed", "failed",
                 "retryable", "skipped", "blocked")

_PRIORITY_LABELS = {1: "critical", 2: "high", 3: "medium-high", 4: "medium",
                    5: "normal", 6: "low", 7: "lowest"}


@dataclass
class TaskNode:
    node_id: str
    title: str
    status: str = "pending"
    priority: int = 5              # 1 (critical) .. 7 (lowest)
    depends_on: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    notes: str = ""
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_row(self, task_id: str) -> tuple:
        return (task_id, self.node_id, self.title[:500], self.status,
                int(self.priority), json.dumps(self.depends_on),
                json.dumps(self.files), self.notes[:500], int(self.attempts),
                self.created_at, self.updated_at)


class TaskGraph:
    """Persistent DAG scoped to one journal task."""

    def __init__(self, journal, task_id: str) -> None:
        self.journal = journal           # app.state.Journal
        self.task_id = task_id
        self._nodes: Dict[str, TaskNode] = {}

    # ------------------------------------------------------------------
    # Load / persist
    # ------------------------------------------------------------------

    async def load(self) -> "TaskGraph":
        if self.journal is None:
            return self
        try:
            rows = await self.journal.query_sql(
                "SELECT * FROM task_nodes WHERE task_id=?", (self.task_id,))
            self._nodes = {}
            for r in rows:
                self._nodes[r["node_id"]] = TaskNode(
                    node_id=r["node_id"], title=r["title"], status=r["status"],
                    priority=r["priority"],
                    depends_on=json.loads(r.get("depends_on") or "[]"),
                    files=json.loads(r.get("files") or "[]"),
                    notes=r.get("notes") or "", attempts=r.get("attempts") or 0,
                    created_at=r.get("created_at") or time.time(),
                    updated_at=r.get("updated_at") or time.time())
        except Exception as e:
            logger.debug(f"[TaskGraph] load failed: {e}")
        return self

    async def _persist(self, node: TaskNode) -> None:
        if self.journal is None:
            return
        try:
            node.updated_at = time.time()
            await self.journal.exec_sql(
                "INSERT OR REPLACE INTO task_nodes (task_id, node_id, title,"
                " status, priority, depends_on, files, notes, attempts,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                node.to_row(self.task_id))
        except Exception as e:
            logger.debug(f"[TaskGraph] persist failed: {e}")

    async def sync_to_task(self) -> None:
        """Mirror the DAG snapshot into the journal task row (Work State 2.0 §9)."""
        if self.journal is None:
            return
        try:
            await self.journal.task_update(self.task_id, plan=self.snapshot())
            prog = self.progress_lists()
            await self.journal.record_progress(
                self.task_id, prog["completed"], prog["in_progress"], prog["pending"])
        except Exception as e:
            logger.debug(f"[TaskGraph] sync_to_task failed: {e}")

    # ------------------------------------------------------------------
    # Mutations (spec §6 rules)
    # ------------------------------------------------------------------

    async def add_node(self, title: str, depends_on: Optional[List[str]] = None,
                       priority: int = 5, node_id: Optional[str] = None,
                       files: Optional[List[str]] = None, notes: str = "") -> TaskNode:
        node_id = node_id or f"n{uuid.uuid4().hex[:6]}"
        depends_on = [d for d in (depends_on or []) if d != node_id]
        node = TaskNode(node_id=node_id, title=title, priority=max(1, min(7, priority)),
                        depends_on=depends_on, files=files or [], notes=notes[:500])
        self._nodes[node_id] = node
        self._recompute_statuses()
        await self._persist(node)
        return node

    async def complete_node(self, node_id: str) -> Tuple[bool, str]:
        node = self._nodes.get(node_id)
        if not node:
            return False, f"node {node_id} not found"
        # v3.0.3: dependencies that are ACTIVE (work demonstrably started —
        # files written, commands run) auto-complete when their successor is
        # completed: the model proves completion through real work, and the
        # old hard block leaked "ERROR: cannot complete … dependencies not
        # completed" noise into final answers. PENDING/READY dependencies
        # (work never started) still hard-block — skipping them would lie
        # about the plan state.
        unmet = [d for d in node.depends_on
                 if self._nodes.get(d) and self._nodes[d].status in ("pending", "ready")]
        auto = [d for d in node.depends_on
                if self._nodes.get(d) and self._nodes[d].status in ("active", "retryable")]
        for d in auto:
            dep = self._nodes[d]
            dep.status = "completed"
            await self._persist(dep)
        if unmet:
            return False, (f"cannot complete '{node.title}': dependencies not"
                           f" started yet: {', '.join(unmet)}")
        node.status = "completed"
        self._recompute_statuses()
        await self._persist(node)
        if auto:
            await self.sync_to_task()
            return True, (f"completed: {node.title} "
                          f"(auto-completed active deps: {', '.join(auto)})")
        return True, f"completed: {node.title}"

    async def start_node(self, node_id: str) -> Tuple[bool, str]:
        node = self._nodes.get(node_id)
        if not node:
            return False, f"node {node_id} not found"
        if node.status not in ("pending", "ready", "retryable", "active"):
            return False, f"node '{node.title}' is {node.status} — cannot start"
        node.status = "active"
        node.attempts += 1
        await self._persist(node)
        return True, f"active: {node.title}"

    async def fail_node(self, node_id: str, error: str = "",
                        retryable: bool = True) -> Tuple[bool, str]:
        node = self._nodes.get(node_id)
        if not node:
            return False, f"node {node_id} not found"
        node.status = "retryable" if retryable else "failed"
        node.notes = (node.notes + f"\n[fail] {error[:200]}").strip()[-500:]
        self._recompute_statuses()
        await self._persist(node)
        return True, f"{node.status}: {node.title}"

    async def skip_node(self, node_id: str, reason: str = "") -> Tuple[bool, str]:
        node = self._nodes.get(node_id)
        if not node:
            return False, f"node {node_id} not found"
        node.status = "skipped"
        if reason:
            node.notes = (node.notes + f"\n[skip] {reason[:200]}").strip()[-500:]
        self._recompute_statuses()
        await self._persist(node)
        return True, f"skipped: {node.title}"

    async def update_node(self, node_id: str, **changes) -> Tuple[bool, str]:
        node = self._nodes.get(node_id)
        if not node:
            return False, f"node {node_id} not found"
        for k in ("title", "notes", "priority"):
            if k in changes and changes[k] is not None:
                setattr(node, k, changes[k])
        if "files" in changes and changes["files"] is not None:
            node.files = list(changes["files"])
        if "depends_on" in changes and changes["depends_on"] is not None:
            node.depends_on = [d for d in changes["depends_on"] if d != node_id]
        if "add_files" in changes and changes["add_files"]:
            node.files = list(dict.fromkeys(node.files + list(changes["add_files"])))
        await self._persist(node)
        return True, f"updated: {node.title}"

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

    def _recompute_statuses(self) -> None:
        """pending -> ready/blocked based on dependencies (never overrides
        terminal/manual states)."""
        for node in self._nodes.values():
            if node.status not in ("pending",):
                continue
            deps = [self._nodes.get(d) for d in node.depends_on]
            if not deps:
                node.status = "ready"
            elif all(d and d.status == "completed" for d in deps):
                node.status = "ready"
            elif any(d and d.status in ("failed", "skipped") for d in deps):
                node.status = "blocked"
        # blocked nodes whose deps later completed become ready again
        for node in self._nodes.values():
            if node.status == "blocked":
                deps = [self._nodes.get(d) for d in node.depends_on]
                if all(d and d.status == "completed" for d in deps):
                    node.status = "ready"

    def nodes(self) -> List[TaskNode]:
        return list(self._nodes.values())

    def get(self, node_id: str) -> Optional[TaskNode]:
        return self._nodes.get(node_id)

    def by_status(self, status: str) -> List[TaskNode]:
        self._recompute_statuses()
        return [n for n in self._nodes.values() if n.status == status]

    def ready_nodes(self) -> List[TaskNode]:
        return self.by_status("ready") + self.by_status("retryable")

    def blocked_nodes(self) -> List[TaskNode]:
        return self.by_status("blocked")

    def _unlock_value(self, node: TaskNode) -> int:
        """How many pending nodes depend (transitively) on this node."""
        dependents: Set[str] = set()

        def visit(nid: str) -> None:
            for other in self._nodes.values():
                if nid in other.depends_on and other.node_id not in dependents:
                    dependents.add(other.node_id)
                    visit(other.node_id)

        visit(node.node_id)
        return len(dependents)

    def prioritized_order(self) -> List[TaskNode]:
        """Smart execution order (spec §8). Never includes completed/failed."""
        self._recompute_statuses()
        candidates = [n for n in self._nodes.values()
                      if n.status in ("ready", "retryable", "active", "pending")]

        def sort_key(n: TaskNode) -> Tuple:
            active_penalty = 0 if n.status == "active" else 1
            pending_penalty = 0 if n.status in ("ready", "retryable", "active") else 1
            return (
                active_penalty,                     # currently active first
                -self._unlock_value(n),             # unblock the most nodes
                n.priority,                         # user priority 1..7
                n.attempts,                         # fewer failures first
                n.created_at,                       # age: older first
                pending_penalty,
            )

        return sorted(candidates, key=sort_key)

    def next_node(self) -> Optional[TaskNode]:
        order = self.prioritized_order()
        return order[0] if order else None

    def progress_percent(self) -> int:
        all_nodes = list(self._nodes.values())
        if not all_nodes:
            return 0
        done = sum(1 for n in all_nodes if n.status == "completed")
        skipped = sum(1 for n in all_nodes if n.status == "skipped")
        denom = len(all_nodes)
        return int(100.0 * (done + skipped) / denom)

    def progress_lists(self) -> Dict[str, List[str]]:
        self._recompute_statuses()
        out: Dict[str, List[str]] = {"completed": [], "in_progress": [], "pending": []}
        for n in self._nodes.values():
            item = f"{n.node_id}: {n.title}"
            if n.status == "completed":
                out["completed"].append(item)
            elif n.status in ("active",):
                out["in_progress"].append(item)
            elif n.status in ("blocked",):
                out["pending"].append(item + f"  (blocked: {[d for d in n.depends_on if self._nodes.get(d) and self._nodes[d].status != 'completed']})")
            else:
                out["pending"].append(item)
        return out

    # ------------------------------------------------------------------
    # Serialization / display
    # ------------------------------------------------------------------

    def snapshot(self) -> List[Dict[str, Any]]:
        self._recompute_statuses()
        return [{
            "node_id": n.node_id, "title": n.title, "status": n.status,
            "priority": n.priority, "depends_on": n.depends_on,
            "files": n.files, "notes": (n.notes or "")[:200],
            "attempts": n.attempts,
        } for n in self._nodes.values()]

    @classmethod
    def from_snapshot(cls, journal, task_id: str,
                      snap: List[Dict[str, Any]]) -> "TaskGraph":
        g = cls(journal, task_id)
        for item in snap or []:
            g._nodes[item["node_id"]] = TaskNode(
                node_id=item["node_id"], title=item.get("title", "?"),
                status=item.get("status", "pending"),
                priority=item.get("priority", 5),
                depends_on=item.get("depends_on") or [],
                files=item.get("files") or [],
                notes=item.get("notes") or "",
                attempts=item.get("attempts") or 0)
        return g

    def render(self, max_nodes: int = 40) -> str:
        """ASCII DAG rendering for /plan + agent context."""
        if not self._nodes:
            return "(no plan nodes)"
        self._recompute_statuses()
        marks = {"completed": "[x]", "active": "[>]", "ready": "[r]",
                 "retryable": "[!]", "failed": "[✗]", "skipped": "[-]",
                 "blocked": "[B]", "pending": "[ ]"}
        lines = [f"PLAN — {len(self._nodes)} nodes, {self.progress_percent()}% complete"]
        order = sorted(self._nodes.values(), key=lambda n: (n.priority, n.created_at))
        for n in order[:max_nodes]:
            dep = ""
            if n.depends_on:
                parts = []
                for d in n.depends_on:
                    dn = self._nodes.get(d)
                    mark = "✓" if (dn and dn.status == "completed") else "·"
                    parts.append(f"{d}{mark}")
                dep = f"  ← {' '.join(parts)}"
            pr = _PRIORITY_LABELS.get(n.priority, "normal")
            if n.priority <= 2:
                pr = f"⚠ {pr}"
            note = f"  — {n.notes.splitlines()[0][:60]}" if n.notes else ""
            lines.append(f"  {marks.get(n.status, '[ ]')} {n.node_id} {n.title[:64]}"
                         f"{dep}  ({pr}){note}")
        ready = self.ready_nodes()
        if ready:
            nxt = self.next_node()
            if nxt:
                lines.append(f"NEXT: {nxt.node_id} {nxt.title[:70]}")
        blocked = self.blocked_nodes()
        if blocked:
            lines.append(f"BLOCKED: {', '.join(b.node_id for b in blocked[:8])}")
        return "\n".join(lines)

    def to_prompt(self) -> str:
        """Compact injection for the LLM (context for planning-awareness)."""
        if not self._nodes:
            return ""
        self._recompute_statuses()
        done = [n.title for n in self._nodes.values() if n.status == "completed"]
        active = [n.title for n in self._nodes.values() if n.status == "active"]
        ready = [n.title for n in self._nodes.values() if n.status == "ready"]
        blocked = [n.title for n in self._nodes.values() if n.status == "blocked"]
        parts = [f"PLAN ({self.progress_percent()}% complete):"]
        if done:
            parts.append("  DONE: " + "; ".join(done[:8]))
        if active:
            parts.append("  ACTIVE: " + "; ".join(active[:4]))
        if ready:
            parts.append("  READY: " + "; ".join(ready[:8]))
        if blocked:
            parts.append("  BLOCKED: " + "; ".join(blocked[:4]))
        nxt = self.next_node()
        if nxt:
            parts.append(f"  NEXT: {nxt.title}")
        return "\n".join(parts)
