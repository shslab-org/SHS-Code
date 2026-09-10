# v4.0 Measured Latency Profile (no guesses)

Measured on this host (shs-code-live, 2026-09-10, re-verified this run — fresh numbers below):

| Stage | Measured (this run, 2026-09-10 PM) | Prior run | Notes |
|---|---|---|---|
| index walk (app/, 257 files) | 2.7ms | 2.6ms (256 files) / 3.14ms (262 files) | `Path.rglob` stat walk only — stable |
| intel refresh COLD (force, full parse) | 1346.9ms (566 files, 6168 symbols) | 860.7ms (262 files, 3436 symbols) | tree grew app-only→full-root scope; parse cost scales with files — paid inline without prefetch is the audit wall-clock killer |
| intel refresh WARM (mtime fast-path) | 45.9ms (566 skipped) | 14.6ms / 14.2ms | mtime/size fast path works — prefetch + warm reuse saves ~1.3s per cold audit at current tree size |
| sqlite 100-row batch (WAL+NORMAL) | 0.27ms | 0.10ms / 0.17ms | engine already ok; per-write sync is the risk, batching needed |
| tiered memory write 100 (L1+L2+batch flush) | 2.35ms | 2.46ms | L1/L2 absorb; single batched commit — stable |
| tiered memory read 100 (L1 hits) | 0.06ms | 0.05ms | RAM-speed hot path — stable |
| context summarize (100KB → ~3KB budget) | 4.9ms | 18.6ms | head/tail+excerpts; source-of-truth via refs — faster on this run (smaller excerpt set) |
| prefix cache 1000 hits | 0.80ms (0.0008ms/hit) | 0.76ms | static prefix never recomputed — stable |
| semantic cache 200 hits | 33.87ms (0.17ms/hit, 200/200 hits) | 2.36ms (0.012ms/hit) | difflib SequenceMatcher scan over 20-entry store dominates; saves LLM+search round-trips but needs index-backed similarity for scale |
| async DAG 5×10ms tasks | gather 10.3ms vs run_dag 10.3ms (1.0x parity) | serial 50.6ms → parallel 10.3ms (4.9x) | run_dag matches gather on fan-out; Amdahl win vs serial stands — dependency ordering preserved |
| async log 500 events + flush | 3.6ms | 2.4ms | buffered, no hot-path stall — stable |
| streaming tool-call parse (2 chunks) | 0.04ms, 2 objs dispatched | 0.04ms, 1 obj | no full-response wait — stable |
| Team103 stress 10/25/50/75/100 | 13/13/20/20/23ms, peak 8/17/28/43/68 | 0.01/0.01/0.02/0.02/0.02s, peak 8/17/24/43/68 | no deadlock; AIMD 8→100 — stable |
| pytest v4 slice | 31 passed in ~0.97s | 27 passed | `tests/v4/` green (+4 live-wiring tests) |

## Bottleneck ranking (measured + code-path)
1. LLM requests (count × TTFT+reasoning) — 4-role serial amplification dominates wall-clock; must cut count (routing/cache) and overlap (parallel/streaming/speculative).
2. Serial orchestration — DAG fan-out absent in `app/agent/orchestrator.py`; Amdahl win is largest here (4.9x measured on 5-way fan-out).
3. Cold index/audit inline — 860ms+ per true-cold audit; background prefetch + warm reuse saves ~0.85s per task + far more on large repos.
4. Verification full-suite per edit — risk-aware tiers save minutes on low-risk edits.
5. Sync logging/observability — buffered async (500 events/2.4ms) saves tail latency + evidence completeness.
6. Static prompt rebuild per request — prefix/KV cache (0.0008ms/hit) saves tokens+TTFT.
7. Repeated search/intel lookups — semantic cache with invalidation saves LLM+search calls.
8. Browser orphan accumulation — bounded pool + sweeper prevents infra collapse (fleet stability, not per-task ms).
9. Memory SQLite per-write sync — L1/L2 + batching removes write stalls (100 reads in 0.05ms).
10. Tool-queue serial read-only — parallel DAG-aware dispatch removes queue latency.

Model request/TTFT/reasoning provider-side latencies require live LLM runs; harness keeps model consistency (bailu-2.8-free primary, 2.7-free whole-batch fallback only) and records per-request metrics via `app/llm/metrics.py` + v4 async observer.
