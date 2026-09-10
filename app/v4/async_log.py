"""OPT-16: Async observability — buffered JSONL, monotonic ts, task/worker/correlation IDs, no hot-path stall."""
from __future__ import annotations
import asyncio, json, time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

@dataclass
class LogEvent:
    event_id: str
    ts_mono: float
    ts_wall: float
    task_id: str
    worker_id: str
    correlation_id: str
    tool: str
    detail: str

class AsyncEventLog:
    def __init__(self, path: str | Path, buf_size: int = 5000, flush_every: int = 200):
        self.path = Path(path); self.buf: deque[str] = deque(maxlen=buf_size)
        self.flush_every = flush_every; self._n = 0; self._seq = 0
        self.dropped = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def emit(self, task_id: str, worker_id: str, correlation_id: str, tool: str, detail: str):
        self._seq += 1
        ev = {"event_id": f"e{self._seq}", "ts_mono": time.monotonic(), "ts_wall": time.time(),
              "task_id": task_id, "worker_id": worker_id, "correlation_id": correlation_id,
              "tool": tool, "detail": detail[:4000]}
        line = json.dumps(ev)
        if len(self.buf) >= self.buf.maxlen: self.dropped += 1
        self.buf.append(line); self._n += 1
        if self._n % self.flush_every == 0:
            self.flush_sync()
    def flush_sync(self):
        if not self.buf: return 0
        with open(self.path, "a", encoding="utf-8") as f:
            while self.buf: f.write(self.buf.popleft() + "\n")
        return self._n
    async def flush(self):
        await asyncio.to_thread(self.flush_sync)
    def stats(self): return {"buffered": len(self.buf), "emitted": self._n, "dropped": self.dropped}
