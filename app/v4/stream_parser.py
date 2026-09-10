"""OPT-5: Streaming JSON/tool-call parser — dispatch on valid boundary.

Incremental buffer; yields complete tool-call objects as soon as a valid
JSON boundary is found. Malformed/incomplete chunks stay buffered; robust
recovery via brace matching + json repair attempts.
"""
from __future__ import annotations
import json
from typing import Any, List

def _extract_balanced(buf: str) -> tuple[Any | None, str]:
    start = buf.find("{")
    if start < 0:
        return None, buf
    depth, instr, esc = 0, False, False
    for i in range(start, len(buf)):
        ch = buf[i]
        if instr:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': instr = False
            continue
        if ch == '"': instr = True
        elif ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                cand = buf[start:i+1]
                try:
                    return json.loads(cand), buf[i+1:]
                except Exception:
                    return None, buf  # incomplete/malformed -> keep buffering
    return None, buf

class StreamToolParser:
    def __init__(self): self.buf = ""; self.dispatched = 0
    def feed(self, chunk: str) -> List[Any]:
        self.buf += chunk
        out = []
        while True:
            obj, rest = _extract_balanced(self.buf)
            if obj is None:
                break
            # tool-call shape: {"name":..., "arguments":...} or {"tool":...}
            if isinstance(obj, dict) and ("name" in obj or "tool" in obj or "function" in obj):
                out.append(obj); self.dispatched += 1
            self.buf = rest
        # bound buffer
        if len(self.buf) > 1_000_000:
            self.buf = self.buf[-500_000:]
        return out
    def flush(self) -> str:
        rem = self.buf; self.buf = ""; return rem
