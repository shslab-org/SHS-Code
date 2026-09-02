from __future__ import annotations

"""
SHS Code — Activity Bus
=======================
Lightweight publish/subscribe bus for live agent activity visibility (spec §32).

Emitters:  LLM layer (thinking / rate-limit waits), agents (steps),
           tool executor (tool_start / tool_end), journal (checkpoints).
Subscriber: the CLI REPL (prints concise activity lines), channels, tests.

This is intentionally dependency-free and synchronous-safe: emit() never
raises, never blocks, and silently drops subscriber errors so that UI
problems can never break the agent loop.
"""

import threading
from typing import Any, Callable

Subscriber = Callable[[str, dict], None]


class ActivityBus:
    """Global activity event bus (singleton semantics via class-level state)."""

    _subscribers: list[Subscriber] = []
    _lock = threading.Lock()

    @classmethod
    def subscribe(cls, fn: Subscriber) -> None:
        with cls._lock:
            if fn not in cls._subscribers:
                cls._subscribers.append(fn)

    @classmethod
    def unsubscribe(cls, fn: Subscriber) -> None:
        with cls._lock:
            if fn in cls._subscribers:
                cls._subscribers.remove(fn)

    @classmethod
    def unsubscribe_all(cls) -> None:
        with cls._lock:
            cls._subscribers.clear()

    @classmethod
    def emit(cls, kind: str, **data: Any) -> None:
        """Emit an activity event. Never raises. kind is a short machine label.

        Standard kinds:
          llm_start, llm_end, step, tool_start, tool_end, tool_error,
          rate_limit_wait, rate_limit_resume, checkpoint, task_start,
          task_complete, task_error, provider_switch, model_switch,
          memory_recall, skill_injected
        """
        with cls._lock:
            subs = list(cls._subscribers)
        for fn in subs:
            try:
                fn(kind, data)
            except Exception:
                # UI failures must never propagate into the agent loop.
                pass


def emit(kind: str, **data: Any) -> None:
    """Module-level convenience wrapper."""
    ActivityBus.emit(kind, **data)
