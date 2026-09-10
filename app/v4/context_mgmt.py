"""OPT-10: Task-relevant, dependency-aware, loss-aware context management.

Large tool outputs -> head/tail + structured summary + excerpts + refs.
Source-of-truth preserved via artifact refs for re-retrieval.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List

@dataclass
class ContextChunk:
    ref: str
    summary: str
    excerpts: List[str]
    head: str
    tail: str
    full_len: int
    truncated: bool

def summarize_output(ref: str, text: str, budget: int = 4000, head_n: int = 1500, tail_n: int = 1500) -> ContextChunk:
    n = len(text)
    if n <= budget:
        return ContextChunk(ref, text[:budget], [], text, "", n, False)
    head, tail = text[:head_n], text[-tail_n:]
    # relevant excerpts: lines with error/fail/def/class keywords
    keys = ("error","fail","exception","traceback","def ","class ","assert","warning")
    lines = text.splitlines()
    ex = [ln[:300] for ln in lines if any(k in ln.lower() for k in keys)][:10]
    omitted = n - head_n - tail_n
    summary = f"{head}\n\n[… {omitted} chars omitted — full artifact at {ref} …]\n\n{tail}"
    if ex: summary += "\n\nKey excerpts:\n" + "\n".join(f"- {e}" for e in ex)
    return ContextChunk(ref, summary, ex, head, tail, n, True)

def assemble_context(chunks: List[ContextChunk], max_chars: int = 24000) -> str:
    out, total = [], 0
    for c in chunks:
        s = f"\n### [{c.ref}]\n{c.summary}\n"
        if total + len(s) > max_chars:
            out.append(f"\n[… context budget {max_chars} reached; remaining refs available on demand …]")
            break
        out.append(s); total += len(s)
    return "".join(out)
