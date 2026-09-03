from __future__ import annotations

"""
SHS Code — Project Intelligence Cache (spec §3)
================================================
Persistent, incremental symbol/import index per project.

Storage:
  ~/.shscode/intel/<sha1(abs_root)[:16]>/index.db   (SQLite, WAL)

Incremental updates (spec §3: "update only necessary indexes"):
  - each file is keyed by (path, mtime, size)
  - a file is reindexed ONLY when its mtime/size changed or it is new
  - files that disappeared are dropped
  - a full walk still visits every path (cheap stat calls), but parsing
    (the expensive part) only happens for changed files

Thread-safe via an RLock around the single connection; async callers
wrap calls in asyncio.to_thread via the ProjectIndex facade.
"""

import hashlib
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.intelligence.indexer import (
    LANGUAGE_BY_EXT, FileIndex, index_file, read_source, walk_source_files,
)
from app.logger import logger
from app import env


def _intel_root() -> Path:
    """Resolve the intel root at CALL time (respects SHSCODE_HOME changes
    — required for test isolation and runtime home switching)."""
    return env.home_dir() / "intel"


INTEL_ROOT = _intel_root()  # module-level convenience (tests should use env)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    language    TEXT NOT NULL,
    lines       INTEGER NOT NULL DEFAULT 0,
    mtime       REAL NOT NULL,
    size        INTEGER NOT NULL,
    indexed_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS symbols (
    path     TEXT NOT NULL,
    name     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    line     INTEGER NOT NULL,
    end_line INTEGER NOT NULL DEFAULT 0,
    signature TEXT NOT NULL DEFAULT '',
    doc      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS imports (
    path   TEXT NOT NULL,
    module TEXT NOT NULL,
    kind   TEXT NOT NULL,
    names  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);
CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(module);
CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime);
"""


def project_cache_dir(root: Path) -> Path:
    key = hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:16]
    return _intel_root() / key


class IntelligenceCache:
    """SQLite-backed incremental project index. One instance per project."""

    def __init__(self, root: Path, max_files: int = 20000) -> None:
        self.root = Path(root).resolve()
        self.max_files = max_files
        self.dir = project_cache_dir(self.root)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "index.db"
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # -- plumbing ---------------------------------------------------------

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            self._connection().executescript(_SCHEMA)
            self._connection().commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _wipe_file(self, path: str) -> None:
        conn = self._connection()
        conn.execute("DELETE FROM files WHERE path=?", (path,))
        conn.execute("DELETE FROM symbols WHERE path=?", (path,))
        conn.execute("DELETE FROM imports WHERE path=?", (path,))

    # -- incremental refresh (spec §3) -------------------------------------

    def refresh(self, force: bool = False) -> Dict[str, int]:
        """Walk the tree; reindex only new/changed files; drop vanished.
        Returns stats: {files, symbols, changed, removed, skipped, ms}."""
        t0 = time.monotonic()
        with self._lock:
            conn = self._connection()
            cached: Dict[str, Tuple[float, int]] = {
                r["path"]: (r["mtime"], r["size"])
                for r in conn.execute("SELECT path, mtime, size FROM files")
            }
        found = walk_source_files(self.root, self.max_files)
        changed = removed = skipped = 0
        seen = set()

        for p in found:
            rel = str(p.relative_to(self.root))
            seen.add(rel)
            try:
                st = p.stat()
            except OSError:
                continue
            mtime, size = st.st_mtime, st.st_size
            if not force and rel in cached and cached[rel] == (mtime, size):
                skipped += 1
                continue
            lang = LANGUAGE_BY_EXT.get(p.suffix.lower(), "")
            if not lang:
                continue
            source = read_source(p)
            if source is None:
                continue
            symbols, imports = index_file(rel, source, lang)
            with self._lock:
                self._wipe_file(rel)
                conn = self._connection()
                conn.execute(
                    "INSERT INTO files (path, language, lines, mtime, size, indexed_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (rel, lang, source.count("\n") + 1, mtime, size, time.time()))
                conn.executemany(
                    "INSERT INTO symbols (path,name,kind,line,end_line,signature,doc)"
                    " VALUES (?,?,?,?,?,?,?)",
                    [s.to_row() for s in symbols])
                conn.executemany(
                    "INSERT INTO imports (path,module,kind,names) VALUES (?,?,?,?)",
                    [i.to_row() for i in imports])
                conn.commit()
            changed += 1

        with self._lock:
            for rel in set(cached) - seen:
                self._wipe_file(rel)
                removed += 1
            if removed:
                conn = self._connection()
                conn.commit()

        stats = {
            "files": len(found),
            "symbols": self.symbol_count(),
            "changed": changed,
            "removed": removed,
            "skipped": skipped,
            "ms": int((time.monotonic() - t0) * 1000),
        }
        logger.info(f"[Intel] refresh {self.root.name}: {stats}")
        return stats

    def refresh_paths(self, rel_paths: Iterable[str]) -> int:
        """Incremental: reindex ONLY the given changed paths (used after edits)."""
        n = 0
        for rel in rel_paths:
            p = self.root / rel
            if not p.exists():
                with self._lock:
                    self._wipe_file(rel)
                    self._connection().commit()
                continue
            lang = LANGUAGE_BY_EXT.get(p.suffix.lower(), "")
            if not lang:
                continue
            source = read_source(p)
            if source is None:
                continue
            st = p.stat()
            symbols, imports = index_file(rel, source, lang)
            with self._lock:
                self._wipe_file(rel)
                conn = self._connection()
                conn.execute(
                    "INSERT INTO files (path, language, lines, mtime, size, indexed_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (rel, lang, source.count("\n") + 1, st.st_mtime, st.st_size,
                     time.time()))
                conn.executemany(
                    "INSERT INTO symbols (path,name,kind,line,end_line,signature,doc)"
                    " VALUES (?,?,?,?,?,?,?)",
                    [s.to_row() for s in symbols])
                conn.executemany(
                    "INSERT INTO imports (path,module,kind,names) VALUES (?,?,?,?)",
                    [i.to_row() for i in imports])
                conn.commit()
            n += 1
        return n

    # -- queries -------------------------------------------------------------

    def symbol_count(self) -> int:
        with self._lock:
            return self._connection().execute("SELECT COUNT(*) c FROM symbols").fetchone()["c"]

    def search_symbols(self, query: str, kind: Optional[str] = None,
                       limit: int = 30) -> List[Dict[str, Any]]:
        """Symbol search: prefix/substring match, ranked (exact > prefix > substring)."""
        q = query.strip()
        if not q:
            return []
        like = f"%{q}%"
        sql = ("SELECT path, name, kind, line, signature, doc FROM symbols"
               " WHERE name LIKE ?")
        params: List[Any] = [like]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " LIMIT ?"
        params.append(limit * 3)
        with self._lock:
            rows = [dict(r) for r in self._connection().execute(sql, params).fetchall()]

        def rank(r: Dict[str, Any]) -> Tuple[int, int]:
            name = r["name"]
            if name == q:
                return (0, -len(name))
            if name.startswith(q):
                return (1, -len(name))
            # camelCase / snake_case part match (e.g. "auth" -> "AuthService")
            if q.lower() in name.lower():
                return (2, -len(name))
            return (3, -len(name))

        rows.sort(key=rank)
        return rows[:limit]

    def search_imports(self, module: str, limit: int = 30) -> List[Dict[str, Any]]:
        sql = ("SELECT path, module, kind, names FROM imports WHERE module LIKE ?"
               " LIMIT ?")
        with self._lock:
            return [dict(r) for r in self._connection().execute(
                sql, (f"%{module}%", limit)).fetchall()]

    def files_for_symbol(self, name: str) -> List[str]:
        with self._lock:
            return [r["path"] for r in self._connection().execute(
                "SELECT path FROM symbols WHERE name=? ORDER BY path", (name,)).fetchall()]

    def all_symbols(self, limit: int = 5000) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._connection().execute(
                "SELECT path, name, kind, line, signature, doc FROM symbols LIMIT ?",
                (limit,)).fetchall()]

    def language_stats(self) -> Dict[str, int]:
        with self._lock:
            rows = self._connection().execute(
                "SELECT language, COUNT(*) n FROM files GROUP BY language ORDER BY n DESC"
            ).fetchall()
        return {r["language"]: r["n"] for r in rows}

    def file_stats(self) -> Dict[str, Any]:
        with self._lock:
            r = self._connection().execute(
                "SELECT COUNT(*) n, SUM(lines) lines, SUM(size) size FROM files"
            ).fetchone()
        return {"files": r["n"] or 0, "lines": r["lines"] or 0, "bytes": r["size"] or 0}

    def indexed_files(self, prefix: str = "") -> List[str]:
        sql = "SELECT path FROM files"
        params: List[Any] = []
        if prefix:
            sql += " WHERE path LIKE ?"
            params.append(f"{prefix}%")
        sql += " ORDER BY path"
        with self._lock:
            return [r["path"] for r in self._connection().execute(sql, params).fetchall()]

    def source_dir_stats(self) -> List[Dict[str, Any]]:
        """Symbols per top-level dir — architectural weight map."""
        with self._lock:
            rows = self._connection().execute(
                "SELECT substr(path, 1, instr(path || '/', '/') - 1) AS top,"
                " COUNT(*) n FROM symbols GROUP BY top ORDER BY n DESC LIMIT 25"
            ).fetchall()
        return [dict(r) for r in rows]

    def modules_imported_most(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Internal dependency hubs: most-imported modules (spec §2 dependency graph)."""
        with self._lock:
            rows = self._connection().execute(
                "SELECT module, COUNT(*) n FROM imports WHERE module NOT LIKE '%'"
                " GROUP BY module ORDER BY n DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]

    def importers_of(self, path: str) -> List[str]:
        """Reverse dependency: which files import symbols likely from `path`."""
        stem = Path(path).with_suffix("").as_posix().replace("/", ".")
        stem_base = stem.rsplit(".", 1)[-1]
        with self._lock:
            rows = self._connection().execute(
                "SELECT DISTINCT path FROM imports WHERE module LIKE ? OR module LIKE ?",
                (f"%{stem}%", f"%.{stem_base}")).fetchall()
        return [r["path"] for r in rows if r["path"] != path]

    def find_symbol_usages(self, name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Text-level usages of a symbol across indexed files (structural search)."""
        hits: List[Dict[str, Any]] = []
        for rel in self.indexed_files():
            p = self.root / rel
            src = read_source(p)
            if src is None:
                continue
            for i, line in enumerate(src.split("\n"), 1):
                if name in line:
                    hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                    if len(hits) >= limit:
                        return hits
        return hits

    def text_search(self, pattern: str, regex: bool = False, limit: int = 60
                    ) -> List[Dict[str, Any]]:
        """Grep-like text search across indexed source files (bounded)."""
        import re as _re
        hits: List[Dict[str, Any]] = []
        rx = None
        if regex:
            try:
                rx = _re.compile(pattern)
            except _re.error:
                return [{"error": f"invalid regex: {pattern}"}]
        for rel in self.indexed_files():
            if len(hits) >= limit:
                break
            p = self.root / rel
            src = read_source(p)
            if src is None:
                continue
            for i, line in enumerate(src.split("\n"), 1):
                if (rx and rx.search(line)) or (not rx and pattern.lower() in line.lower()):
                    hits.append({"path": rel, "line": i, "text": line.strip()[:240]})
                    if len(hits) >= limit:
                        break
        return hits
