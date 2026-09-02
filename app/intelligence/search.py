from __future__ import annotations

"""
SHS Code — Semantic + Structural Code Search (spec §4)
========================================================
Search modes:
  filename   — fuzzy path match
  text       — plain substring (case-insensitive)
  regex      — regex line search
  symbol     — symbol table lookup (class/function/method/...)
  import     — who imports module X
  usages     — where is symbol S referenced (structural)
  semantic   — concept search: token-expanded relevance scoring over
               symbol names, signatures, docstrings and paths
  callers    — reverse-dependency: files importing symbols from a file

"Where is authentication handled?" → semantic mode expands
auth→{login, session, token, credential, jwt, oauth, password} and ranks
symbols+files by aggregated evidence — locating the architecture, not
just the word "authentication".
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Concept expansion map (domain keywords -> related tokens)
_CONCEPTS: Dict[str, List[str]] = {
    "auth": ["login", "session", "token", "credential", "jwt", "oauth",
             "password", "signin", "signup", "permission", "role", "user"],
    "authentication": ["auth", "login", "session", "token", "credential", "jwt"],
    "authorization": ["permission", "role", "acl", "gate", "policy", "access"],
    "database": ["db", "sqlite", "mysql", "postgres", "schema", "migration",
                 "query", "repository", "dao", "orm", "table"],
    "config": ["settings", "configuration", "env", "toml", "yaml", "json",
               "profile", "options", "preferences"],
    "api": ["route", "endpoint", "controller", "handler", "rest", "graphql",
            "router", "request", "response", "middleware"],
    "test": ["test", "spec", "assert", "mock", "fixture", "conftest", "suite"],
    "ui": ["component", "view", "page", "screen", "widget", "render", "layout",
           "compose", "fragment", "activity"],
    "error": ["error", "exception", "failure", "retry", "fallback", "raise",
              "crash", "recover"],
    "logging": ["log", "logger", "trace", "audit", "telemetry", "debug"],
    "memory": ["memory", "cache", "recall", "forget", "store", "persist", "state"],
    "rate": ["limit", "throttle", "rpm", "quota", "backoff", "retry_after"],
    "git": ["commit", "branch", "push", "pull", "merge", "diff", "checkout"],
    "security": ["secret", "key", "mask", "redact", "encrypt", "hash", "sanitize"],
    "performance": ["speed", "fast", "cache", "async", "parallel", "latency",
                    "optimize", "benchmark"],
    "deployment": ["deploy", "docker", "release", "ci", "pipeline", "publish",
                   "build", "package"],
    "notification": ["notify", "message", "channel", "webhook", "alert", "send"],
    "payment": ["payment", "billing", "invoice", "charge", "subscription", "stripe"],
    "search": ["search", "query", "index", "find", "match", "rank", "score"],
}

_SPLIT_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[A-Za-z]+")
_SPLIT_ANY = re.compile(r"[^A-Za-z0-9]+")


def _tokens(text: str) -> List[str]:
    """Split camelCase / snake_case / kebab into lowercase tokens."""
    out: List[str] = []
    for chunk in _SPLIT_ANY.split(text):
        if not chunk:
            continue
        out.extend(m.group(0).lower() for m in _SPLIT_CAMEL.finditer(chunk))
    return out


def expand_query(query: str) -> List[str]:
    """Expand a natural-language query into related tokens (concept expansion)."""
    toks = _tokens(query)
    expanded = set(toks)
    for t in toks:
        for related in _CONCEPTS.get(t, []):
            expanded.add(related)
        # also match concepts whose key appears in the query
        for key, related in _CONCEPTS.items():
            if t and (key.startswith(t) or t.startswith(key)) and len(t) >= 4:
                expanded.update(related)
    return sorted(expanded)


class SemanticSearch:
    """Relevance scoring over the project's symbol table."""

    def __init__(self, cache) -> None:   # cache: IntelligenceCache
        self.cache = cache

    def _score_symbol(self, q_tokens: List[str], row: Dict[str, Any],
                      path_tokens: List[str]) -> float:
        name_toks = set(_tokens(row["name"]))
        sig_toks = set(_tokens(row.get("signature") or ""))
        doc_toks = set(_tokens((row.get("doc") or "")[:200]))
        blob = name_toks | sig_toks | doc_toks | set(path_tokens)
        score = 0.0
        for qt in q_tokens:
            if qt in name_toks:
                score += 3.0          # strongest: query token in symbol name
            elif qt in sig_toks:
                score += 1.0
            elif qt in doc_toks:
                score += 0.8
            elif qt in path_tokens:
                score += 0.6
            elif qt in blob:
                score += 0.3
        # kind weighting: classes/interfaces are architectural anchors
        if row.get("kind") in ("class", "interface", "type", "object"):
            score *= 1.25
        return score

    def search(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        q_tokens = expand_query(query)
        if not q_tokens:
            return []
        rows = self.cache.all_symbols(limit=20000)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        path_token_cache: Dict[str, List[str]] = {}
        for r in rows:
            path = r["path"]
            if path not in path_token_cache:
                path_token_cache[path] = _tokens(path)
            s = self._score_symbol(q_tokens, r, path_token_cache[path])
            if s >= 2.5:
                hit = dict(r)
                hit["score"] = round(s, 2)
                scored.append((s, hit))
        scored.sort(key=lambda t: -t[0])
        return [h for _, h in scored[:limit]]

    def files_for_concept(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Aggregate symbol hits to file level — 'which files own this concept'."""
        hits = self.search(query, limit=200)
        by_file: Dict[str, Dict[str, Any]] = {}
        for h in hits:
            f = by_file.setdefault(h["path"], {"path": h["path"], "score": 0.0,
                                               "symbols": []})
            f["score"] += h["score"]
            if len(f["symbols"]) < 5:
                f["symbols"].append(f"{h['kind']} {h['name']}")
        out = sorted(by_file.values(), key=lambda x: -x["score"])[:limit]
        return out


def search_filename(cache, pattern: str, limit: int = 25) -> List[str]:
    p = pattern.lower().strip()
    files = cache.indexed_files()
    exact = [f for f in files if Path(f).name.lower() == p]
    startswith = [f for f in files if Path(f).name.lower().startswith(p)]
    contains = [f for f in files if p in f.lower()]
    seen, out = set(), []
    for lst in (exact, startswith, contains):
        for f in lst:
            if f not in seen:
                seen.add(f)
                out.append(f)
            if len(out) >= limit:
                return out
    return out


def search_dispatch(cache, mode: str, query: str, limit: int = 20
                    ) -> Dict[str, Any]:
    """Unified search entry point used by tools + CLI.
    Returns {mode, query, results: [...], count}."""
    if mode == "symbol":
        kind = None
        q = query
        m = re.match(r"^(\w+)\s+(.*)$", query)
        if m and m.group(2) and m.group(1).lower() in (
                "class", "function", "method", "interface", "type", "object",
                "heading"):
            kind, q = m.group(1).lower(), m.group(2)
        rows = cache.search_symbols(q, kind=kind, limit=limit)
        return {"mode": "symbol", "query": query, "results": rows, "count": len(rows)}
    if mode == "filename":
        rows = search_filename(cache, query, limit)
        return {"mode": "filename", "query": query, "results": rows, "count": len(rows)}
    if mode == "text":
        rows = cache.text_search(query, regex=False, limit=limit)
        return {"mode": "text", "query": query, "results": rows, "count": len(rows)}
    if mode == "regex":
        rows = cache.text_search(query, regex=True, limit=limit)
        return {"mode": "regex", "query": query, "results": rows, "count": len(rows)}
    if mode == "import":
        rows = cache.search_imports(query, limit)
        return {"mode": "import", "query": query, "results": rows, "count": len(rows)}
    if mode in ("usages", "usage"):
        rows = cache.find_symbol_usages(query, limit)
        return {"mode": "usages", "query": query, "results": rows, "count": len(rows)}
    if mode in ("semantic", "concept"):
        sem = SemanticSearch(cache)
        rows = sem.files_for_concept(query, limit)
        symbols = sem.search(query, limit=limit)
        return {"mode": "semantic", "query": query, "results": rows,
                "symbols": symbols, "count": len(rows)}
    if mode in ("callers", "importers"):
        rows = cache.importers_of(query)
        return {"mode": "callers", "query": query, "results": rows, "count": len(rows)}
    return {"mode": mode, "query": query, "results": [],
            "error": f"unknown search mode: {mode} (use symbol|filename|text|regex|import|usages|semantic|callers)"}


def format_search_results(res: Dict[str, Any], max_items: int = 20) -> str:
    """Human/LLM-readable rendering of search results."""
    if res.get("error"):
        return f"search error: {res['error']}"
    lines = [f"search[{res['mode']}] \"{res['query']}\" — {res.get('count', 0)} match(es)"]
    for r in (res.get("results") or [])[:max_items]:
        if isinstance(r, str):
            lines.append(f"  {r}")
        elif "path" in r and "name" in r:
            lines.append(f"  {r['path']}:{r.get('line', '?')}  [{r.get('kind')}] "
                         f"{r.get('name')} — {(r.get('signature') or '')[:80]}")
        elif "path" in r and "text" in r:
            lines.append(f"  {r['path']}:{r['line']}  {r['text'][:120]}")
        elif "path" in r and "score" in r:
            syms = ", ".join(r.get("symbols", [])[:4])
            lines.append(f"  {r['path']}  (score {r['score']})  {syms}")
        elif "module" in r:
            lines.append(f"  {r['path']}  imports {r['module']} ({r.get('kind')})")
    if res.get("symbols"):
        lines.append("  top symbols:")
        for s in res["symbols"][:8]:
            lines.append(f"    {s['path']}:{s.get('line', '?')}  [{s['kind']}] "
                         f"{s['name']} (score {s.get('score', '?')})")
    return "\n".join(lines)
