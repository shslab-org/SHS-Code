from __future__ import annotations
"""Shared agent-context bridge.

Lets tools (e.g. skill_manager's one-off guard) read lightweight facts about
the CURRENT agent run — the user's goal, the request kind — without any
tool needing a reference to the agent instance. Values are set by
BaseAgent.run() via set_run_context() and cleared automatically on exit.
"""
from contextvars import ContextVar
from typing import Optional

_ctx_goal: ContextVar[Optional[str]] = ContextVar("shs_goal", default=None)
_ctx_request_kind: ContextVar[Optional[str]] = ContextVar(
    "shs_request_kind", default=None)


def set_run_context(goal: str = "", request_kind: str = "") -> None:
    if goal:
        _ctx_goal.set(goal[:500])
    if request_kind:
        _ctx_request_kind.set(request_kind)


def clear_run_context() -> None:
    _ctx_goal.set(None)
    _ctx_request_kind.set(None)


def get_current_goal() -> str:
    return _ctx_goal.get() or ""


def get_request_kind() -> str:
    return _ctx_request_kind.get() or ""
