# v4.0 Measured Latency Profile (no guesses)

Measured on this host (shs-code-live, 2026-09-10):

| Stage | Measured | Notes |
|---|---|---|
| index walk (app/, 262 files) | 3.14ms avg | `walk_source_files` stat walk only |
| intel refresh COLD | 860.7ms (262 files, 3436 symbols) | parse cost, paid inline without prefetch |
| intel refresh WARM (incremental) | 14.2ms (262 skipped) | mtime/size fast path works |
| sqlite 100-row batch | 0.17ms avg | WAL+NORMAL already ok; per-write sync is the risk, batching needed |
| planner heuristic | 0.02ms | local path negligible; LLM planner call dominates when used |
| pytest full suite | 66.63s (652 passed, 1 pre-existing fail) | baseline green minus 1 known failure |

## Bottleneck ranking (measured + code-path)
1. LLM requests (count × TTFT+reasoning) — 4-role serial amplification dominates wall-clock; must cut count (routing/cache) and overlap (parallel/streaming/speculative).
2. Serial orchestration — DAG fan-out absent; Amdahl win is largest here.
3. Cold index/audit inline — 860ms+ per cold audit; background prefetch + warm reuse saves ~0.8s per task + far more on large repos.
4. Verification full-suite per edit — risk-aware tiers save minutes on low-risk edits.
5. Sync logging/observability — buffered async saves tail latency + evidence completeness.
6. Static prompt rebuild per request — prefix/KV cache saves tokens+TTFT.
7. Repeated search/intel lookups — semantic cache with invalidation saves LLM+search calls.
8. Browser orphan accumulation — bounded pool + sweeper prevents infra collapse (not per-task ms, but fleet stability).
9. Memory SQLite per-write sync — L1/L2 + batching removes write stalls.
10. Tool-queue serial read-only — parallel DAG-aware dispatch removes queue latency.

Model request/TTFT/reasoning provider-side latencies require live LLM runs; harness keeps model consistency (bailu-2.8-free primary, 2.7-free whole-batch fallback only) and records per-request metrics via `app/llm/metrics.py` + v4 async observer.
