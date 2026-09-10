"""OPT-1: Prompt/KV/prefix caching — stable static prefix reuse.

Static system prompt + tool schemas + project context are hashed into a
stable prefix key. Dynamic task state is appended AFTER the prefix so it
never breaks the cached prefix. Invalidation only on static content change.
Provider pass-through: exposes prefix key + reuse flag so litellm/openai
prefix/KV caching can key on it.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Any

def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:32]

@dataclass
class PrefixCache:
    static_parts: list[str] = field(default_factory=list)
    _key: str = ""
    hits: int = 0
    misses: int = 0
    def build(self, *parts: str) -> str:
        key = _h("\n\x00\n".join(parts))
        if key == self._key and self._key:
            self.hits += 1
        else:
            self.misses += 1
            self._key = key
            self.static_parts = list(parts)
        return self._key
    def assemble(self, dynamic: str) -> dict[str, Any]:
        static = "\n".join(self.static_parts)
        return {"prefix_key": self._key, "cache_reuse": bool(self._key),
                "static_len": len(static), "dynamic_len": len(dynamic),
                "messages_static": static, "messages_dynamic": dynamic}
    def invalidate(self):
        self._key = ""; self.static_parts = []
    def stats(self): return {"prefix_key": self._key, "hits": self.hits, "misses": self.misses}
