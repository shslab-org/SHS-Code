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


# v3.1: agent mode in the run context (delegate sub-agents inherit the
# parent's mode instead of hardcoding BUILD).
_ctx_mode: ContextVar[Optional[str]] = ContextVar("shs_mode", default=None)


def set_run_mode(mode: str = "") -> None:
    if mode:
        _ctx_mode.set(str(mode)[:32])


def get_run_mode() -> str:
    return _ctx_mode.get() or ""


def get_run_context() -> dict:
    """Full run context snapshot (goal, request kind, mode)."""
    return {
        "goal": _ctx_goal.get() or "",
        "request_kind": _ctx_request_kind.get() or "",
        "mode": _ctx_mode.get() or "",
    }
