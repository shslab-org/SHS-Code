"""v4.0 optimization tests: cache correctness, DAG, locks, recovery, streaming, speculative, memory, QA, merger."""
from __future__ import annotations
import asyncio, time

def test_opt1_prefix_cache_reuse():
    from app.v4.prefix_cache import PrefixCache
    c = PrefixCache()
    k1 = c.build("SYS", "TOOLS", "CTX")
    a = c.assemble("dyn1")
    k2 = c.build("SYS", "TOOLS", "CTX")
    assert k1 == k2 and c.hits == 1
    c.build("SYS2", "TOOLS", "CTX")
    assert c.misses == 2
    # dynamic never breaks prefix
    assert a["prefix_key"] == k1

def test_opt2_semantic_cache_invalidation():
    from app.v4.semantic_cache import SemanticCache, fingerprint
    sc = SemanticCache(threshold=0.8)
    ctx = fingerprint("root", "main", "epoch1")
    ok, _ = sc.get("list files", ctx)
    assert not ok
    sc.put("list files", ctx, ["a.py"])
    ok, v = sc.get("list files", ctx)
    assert ok and v == ["a.py"]
    # different ctx -> miss (no false positive)
    ok2, _ = sc.get("list files", fingerprint("root", "other", "epoch1"))
    assert not ok2
    n = sc.invalidate_ctx(ctx)
    assert n >= 1
    ok3, _ = sc.get("list files", ctx)
    assert not ok3

def test_opt3_async_dag_parallel_and_serial():
    from app.v4.async_dag import run_dag, DagNode
    import asyncio
    order = []
    async def a():
        await asyncio.sleep(0.02); order.append("a"); return 1
    async def b():
        await asyncio.sleep(0.02); order.append("b"); return 2
    async def d():
        order.append("d"); return 3
    async def main():
        t0 = time.monotonic()
        res = await run_dag([DagNode("a", a), DagNode("b", b), DagNode("d", d, ["a"])])
        dt = time.monotonic() - t0
        assert res == {"a": 1, "b": 2, "d": 3}
        assert dt < 0.15  # parallel, not 3x serial
        assert order.index("d") > order.index("a")  # dependency respected
    asyncio.run(main())

def test_opt5_streaming_parser_boundary():
    from app.v4.stream_parser import StreamToolParser
    p = StreamToolParser()
    out = p.feed('{"name": "bash", "arguments": {"cmd": "ls"}')
    assert out == []  # incomplete buffered
    out = p.feed('} trailing {"name": "read", "arguments": {}}')
    assert len(out) == 2 and out[0]["name"] == "bash"

def test_opt6_speculative_cancel():
    from app.v4.speculative import SpeculativeExecutor
    import asyncio
    async def main():
        ex = SpeculativeExecutor()
        async def slow(): await asyncio.sleep(5); return "late"
        s = ex.speculate("k", slow)
        ex.cancel("k")
        r = await ex.resolve("k")
        assert r is None
        async def fast(): return "ok"
        ex.speculate("k2", fast)
        r2 = await ex.resolve("k2", lambda v: v == "ok")
        assert r2 == "ok"
    asyncio.run(main())

def test_opt8_tiered_memory_batching():
    from app.v4.memory_tiers import TieredMemory
    import asyncio
    async def main():
        m = TieredMemory(":memory:")
        m.put("k1", "v1"); m.put("k2", "v2")
        assert m.get("k1") == "v1"  # L1 hit
        n = await m.flush()
        assert n == 2
        assert m.get("k2") == "v2"
        m.close()
    asyncio.run(main())

def test_opt9_intelligent_memory():
    from app.v4.intel_memory import IntelligentMemory
    im = IntelligentMemory()
    im.add("user prefers python", confidence=0.9)
    im.add("must never delete prod db", confidence=0.95)
    res = im.retrieve("python preference", top_k=3)
    assert any("python" in r.text for r in res)
    # low confidence filtered
    im.add("maybe old fact", confidence=0.1)
    assert all(r.confidence >= 0.25 for r in im.retrieve("fact"))

def test_opt10_context_truncation():
    from app.v4.context_mgmt import summarize_output, assemble_context
    big = "line\n" * 5000 + "ERROR boom\n" + "x" * 20000
    ch = summarize_output("tool:bash", big)
    assert ch.truncated and len(ch.summary) < len(big)
    assert "ERROR" in ch.summary or ch.excerpts
    ctx = assemble_context([ch], max_chars=24000)
    assert len(ctx) <= 26000

def test_opt11_model_routing_modes():
    from app.v4.model_router import ModelRouter
    b = ModelRouter(mode="benchmark")
    assert b.route("summarize")[1] == "bailu-2.8-free"  # consistency
    p = ModelRouter(mode="production")
    assert p.route("summarize logs")[0] == "fast"
    assert p.route("complex debugging")[0] == "strong"

def test_opt12_plan_cache():
    from app.v4.plan_cache import PlanCache
    pc = PlanCache()
    assert pc.get("build api", "py", "s1") is None
    pc.put("build api", "py", "s1", ["step1"])
    assert pc.get("build api", "py", "s1") == ["step1"]
    assert pc.get("build api", "py", "s2") is None  # state change invalidates
    pc.invalidate_on("requirement")

def test_opt13_risk_tiers():
    from app.v4.risk_verify import risk_of, kinds_for_risk
    assert risk_of(["docs.md"]) == "low"
    assert risk_of(["a.py"]*6) == "medium"
    assert risk_of(["schema.sql"], touches_core=True) == "high"
    assert kinds_for_risk("low") == ["build"]

def test_opt14_repair_and_retry():
    from app.v4.recovery import repair_json, retry_async, Checkpoint
    import asyncio
    assert repair_json('{"a": 1') == {"a": 1}
    assert repair_json('xx {"b": 2} yy') == {"b": 2}
    async def main():
        calls = {"n": 0}
        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3: raise RuntimeError("boom")
            return "ok"
        assert await retry_async(flaky, attempts=5, base_s=0.01) == "ok"
    asyncio.run(main())
    c = Checkpoint(); c.save(step=3); assert c.get("step") == 3

def test_opt16_async_log_integrity():
    from app.v4.async_log import AsyncEventLog
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ev.jsonl")
        log = AsyncEventLog(p)
        for i in range(10):
            log.emit("t1", "w1", "c1", "bash", f"cmd {i}")
        log.flush_sync()
        lines = open(p).read().strip().splitlines()
        assert len(lines) == 10

def test_opt17_dedup_and_locks():
    from app.v4.dedup import DedupRegistry
    r = DedupRegistry()
    ok, _ = r.try_claim("w1", "fix login", ["a.py"])
    assert ok
    ok2, why = r.try_claim("w2", "fix login", ["a.py"])
    assert not ok2 and "duplicate" in why
    ok3, why3 = r.try_claim("w2", "other task", ["a.py"])
    assert not ok3 and "file-locked" in why3
    r.release("w1", "fix login", ["a.py"], result="done")
    assert r.cached("fix login", ["a.py"]) == "done"

def test_opt18_merge_conflicts():
    from app.v4.merger import WorkerResult, merge_results
    rs = [WorkerResult("w1", ["a.py"], ["t1"], confidence=0.9),
          WorkerResult("w2", ["a.py", "b.py"], ["t2"], confidence=0.8)]
    m = merge_results(rs)
    assert "a.py" in m.conflicts and m.merged_files == ["a.py", "b.py"]

def test_opt19_continuous_qa_gate():
    from app.v4.cont_qa import ContinuousQA
    import asyncio
    async def main():
        qa = ContinuousQA()
        f = await qa.check_changed(["definitely_missing_xyz_123.py"])
        assert f and not f[0].passed
        ok, _ = qa.final_gate(0.9, 0, 1)
        assert not ok
    asyncio.run(main())

def test_opt20_decompose():
    from app.v4.roles import decompose_goal
    specs = decompose_goal("Build API. Add tests. Write docs.")
    assert len(specs) >= 3
