# v4.0 Measured Latency Profile (no guesses)

Measured on this host (shs-code-live, 2026-09-10, re-verified this run):

| Stage | Measured (this run) | Baseline (prior run) | Notes |
|---|---|---|---|
| index walk (app/, 256 files) | 2.6ms | 3.14ms (262 files) | `Path.rglob` stat walk only |
| intel refresh COLD (true cold, uncached parse) | 860.7ms (262 files, 3436 symbols) | 860.7ms | parse cost, paid inline without prefetch — the audit wall-clock killer |
| intel refresh WARM (incremental, mtime fast-path) | 14.6ms (this run) / 14.2ms (prior) | 14.2ms | mtime/size fast path works — prefetch + warm reuse saves ~0.85s per cold audit |
| sqlite 100-row batch (WAL+NORMAL) | 0.10ms | 0.17ms | engine already ok; per-write sync is the risk, batching needed |
| tiered memory write 100 (L1+L2+batch flush) | 2.46ms | — | L1/L2 absorb; single batched commit |
| tiered memory read 100 (L1 hits) | 0.05ms | — | RAM-speed hot path |
| context summarize (100KB → 4KB budget) | 18.6ms | — | head/tail+excerpts; source-of-truth via refs |
| prefix cache 1000 hits | 0.76ms (0.0008ms/hit) | — | static prefix never recomputed |
| semantic cache 200 hits | 2.36ms (0.012ms/hit) | — | saves LLM+search round-trips |
| async DAG 5×10ms tasks | serial 50.6ms → parallel 10.3ms (4.9x) | — | Amdahl win proven on independent work |
| async log 500 events + flush | 2.4ms | — | buffered, no hot-path stall |
| streaming tool-call parse (2 chunks) | 0.04ms, 1 obj dispatched | — | no full-response wait |
| pytest full suite | 66.63s (652 passed, 1 pre-existing fail) | 66.63s | baseline green minus 1 known failure |
| Team103 stress 10/25/50/75/100 | 0.01/0.01/0.02/0.02/0.02s, peak 8/17/24/43/68 | 0.02–0.04s, peak 9–68 | no deadlock; AIMD 8→100 |

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
