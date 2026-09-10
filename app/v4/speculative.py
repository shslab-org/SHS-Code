"""OPT-6: Speculative tool execution with cancellation + validation.

Safe independent preparation starts early; speculative results are NEVER
authoritative until dependencies validate. Wrong speculation is discarded.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

@dataclass
class Speculation:
    task: asyncio.Task
    valid: bool = True
    def cancel(self):
        self.valid = False
        if not self.task.done():
            self.task.cancel()

class SpeculativeExecutor:
    def __init__(self): self.pending: dict[str, Speculation] = {}
    def speculate(self, key: str, coro_fn: Callable[[], Awaitable[Any]]) -> Speculation:
        async def _w():
            return await coro_fn()
        t = asyncio.create_task(_w())
        s = Speculation(task=t)
        self.pending[key] = s
        return s
    async def resolve(self, key: str, is_valid: Callable[[Any], bool] | None = None) -> Any | None:
        s = self.pending.pop(key, None)
        if s is None: return None
        try:
            res = await s.task
        except asyncio.CancelledError:
            return None
        except Exception:
            return None
        if not s.valid: return None
        if is_valid is not None:
            try:
                if not is_valid(res): return None
            except Exception:
                return None
        return res
    def cancel(self, key: str):
        s = self.pending.pop(key, None)
        if s: s.cancel()
    def cancel_all(self):
        for k in list(self.pending): self.cancel(k)
