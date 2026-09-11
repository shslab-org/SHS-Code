"""FIX SPEC §4 regression: semantic cache correctness + performance.

Locks the §4 fix: exact O(1) fast-path, per-ctx buckets, length-bound
prune, bounded size, thread safety. Semantics preserved from
test_opt2_semantic_cache_invalidation (exact/ctx-isolation/invalidate).
"""
from __future__ import annotations
import threading
import time


def test_semcache_exact_miss_ctx_invalidate():
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache(threshold=0.8)
    ctx = fingerprint("root", "main", "epoch1")
    assert sc.get("list files", ctx) == (False, None)
    sc.put("list files", ctx, ["a.py"])
    ok, v = sc.get("list files", ctx)
    assert ok and v == ["a.py"]
    ok2, _ = sc.get("list files", fingerprint("root", "other", "epoch1"))
    assert not ok2
    assert sc.invalidate_ctx(ctx) >= 1
    assert sc.get("list files", ctx) == (False, None)


def test_semcache_near_match_and_far_miss():
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache(threshold=0.8)
    ctx = fingerprint("root", "main", "epoch1")
    sc.put("list all files in project", ctx, ["b.py"])
    ok, v = sc.get("list all files in projects", ctx)
    assert ok and v == ["b.py"]
    ok2, _ = sc.get("completely unrelated xyzzy foo", ctx)
    assert not ok2


def test_semcache_stale_counts_and_misses():
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache(threshold=0.8, ttl_s=0.05)
    ctx = fingerprint("r", "b", "e")
    sc.put("hello world", ctx, 123)
    time.sleep(0.08)
    ok, _ = sc.get("hello world", ctx)
    assert not ok
    assert sc.metrics.stale >= 1


def test_semcache_same_query_multi_ctx():
    # Old dict-keyed-by-query impl overwrote across ctx; keyed by (ctx, q) now.
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache()
    ca, cb = fingerprint("a"), fingerprint("b")
    sc.put("same q", ca, "VA")
    sc.put("same q", cb, "VB")
    assert sc.get("same q", ca) == (True, "VA")
    assert sc.get("same q", cb) == (True, "VB")


def test_semcache_bounded_and_concurrent():
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache(max_entries=100)
    ctx = fingerprint("c")
    for i in range(150):
        sc.put(f"q{i}", ctx, i)
    assert sc.stats()["size"] <= 100
    errs: list = []

    def w():
        try:
            for j in range(200):
                sc.put(f"q{j % 50}", ctx, j)
                sc.get(f"q{j % 50}", ctx)
        except Exception as e:  # pragma: no cover
            errs.append(e)

    ts = [threading.Thread(target=w) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs


def test_semcache_perf_exact_fast_and_miss_bounded():
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache(threshold=0.82)
    ctx = fingerprint("root", "main", "epoch1")
    for i in range(1000):
        sc.put(f"query number {i} list files in project {i % 10}", ctx, [f"{i}.py"])
    t0 = time.monotonic()
    for _ in range(50):
        sc.get("query number 5 list files in project 5", ctx)
    exact_ms = (time.monotonic() - t0) / 50 * 1000
    assert exact_ms < 1.0, f"exact fast-path too slow: {exact_ms:.2f}ms"
    t0 = time.monotonic()
    for _ in range(20):
        sc.get("completely unrelated query xyzzy foo bar", ctx)
    miss_ms = (time.monotonic() - t0) / 20 * 1000
    # Before fix: ~35-40ms miss at n=1000 (full difflib scan). Fixed must
    # stay well under that via length-prune + per-ctx bucket.
    assert miss_ms < 15.0, f"miss scan too slow: {miss_ms:.2f}ms"
