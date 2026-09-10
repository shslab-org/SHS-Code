"""OPT-8: Memory L1-L4 — L1 in-process LRU, L2 session cache, L3 SQLite WAL+batch, L4 Markdown durable.

Frequently accessed state stays in RAM. Small writes batch + async persist.
Crash durability via WAL + periodic flush.
"""
from __future__ import annotations
import asyncio, collections, sqlite3, threading, time
from pathlib import Path
from typing import Any, Dict, List, Optional

class LRU:
    def __init__(self, cap: int = 512):
        self.cap = cap; self._d: collections.OrderedDict[str, Any] = collections.OrderedDict()
        self.hits = 0; self.misses = 0
    def get(self, k: str):
        if k in self._d:
            self._d.move_to_end(k); self.hits += 1; return True, self._d[k]
        self.misses += 1; return False, None
    def put(self, k: str, v: Any):
        self._d[k] = v; self._d.move_to_end(k)
        while len(self._d) > self.cap: self._d.popitem(last=False)
    def stats(self): return {"size": len(self._d), "hits": self.hits, "misses": self.misses}

class TieredMemory:
    """L1 process LRU + L2 session dict + L3 SQLite (WAL, batched) + L4 markdown file."""
    def __init__(self, db_path: str | Path = ":memory:", md_path: str | Path | None = None, l1_cap: int = 512):
        self.l1 = LRU(l1_cap)
        self.l2: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL"); self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT, updated REAL)")
        self._conn.commit()
        self._pending: Dict[str, str] = {}
        self.md_path = Path(md_path) if md_path else None
        self.writes_batched = 0; self.flushes = 0
    def get(self, k: str):
        ok, v = self.l1.get(k)
        if ok: return v
        if k in self.l2: self.l1.put(k, self.l2[k]); return self.l2[k]
        with self._lock:
            r = self._conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        if r: self.l2[k] = r[0]; self.l1.put(k, r[0]); return r[0]
        return None
    def put(self, k: str, v: str, durable: bool = True):
        self.l1.put(k, v); self.l2[k] = v
        if durable: self._pending[k] = v
    async def flush(self):
        if not self._pending: return 0
        batch = dict(self._pending); self._pending.clear()
        def _w():
            with self._lock:
                now = time.time()
                self._conn.executemany("INSERT OR REPLACE INTO kv VALUES(?,?,?)", [(k, v, now) for k, v in batch.items()])
                self._conn.commit()
        await asyncio.to_thread(_w)
        self.writes_batched += len(batch); self.flushes += 1
        if self.md_path:
            try:
                def _md():
                    self.md_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.md_path, "a", encoding="utf-8") as f:
                        for k, v in batch.items(): f.write(f"\n## {k}\n{v}\n")
                await asyncio.to_thread(_md)
            except Exception: pass
        return len(batch)
    def stats(self): return {"l1": self.l1.stats(), "l2_size": len(self.l2), "pending": len(self._pending), "writes_batched": self.writes_batched, "flushes": self.flushes}
    def close(self):
        try: self._conn.commit(); self._conn.close()
        except Exception: pass
