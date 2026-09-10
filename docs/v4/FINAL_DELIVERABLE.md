# v4.0.0 Final Deliverable — 20-Point Report (measured, source-first)

Date: 2026-09-10 · Host: shs-code-live · Branch: main · Version: 4.0.0
Method: SOURCE → MEASURE → DESIGN → IMPLEMENT → TEST → BENCHMARK → OPTIMIZE. No guesses.

## 1. Subsystems inspected
Full tree `app/` + agent core (`base.py` 1236L, `react.py`, `shscode.py`), planner (376L), executor (`toolcall.py` 839L), 25 tools, provider/LLM stack (`llm.py` 1143L + litellm/bedrock/mistral/fallback/rate_limiter/retry/offline_router), streaming (852L), context/compaction/message (647L), memory (long/short + session DB + Markdown), journal/checkpoint (`state.py`), task DAG/queue/pool, recovery/retry, code search/AST indexer/semantic search/project_intel, browser, MCP, skills, delegation, parallel executor, orchestrator (4-role serial), verification (312L), gates, session/resume, config/headless, logging/observability, tests (39 files), Compare/ benchmarks, perf hot-paths. Inventory: `docs/v4/EXPLORATION.md`.

## 2. Current architecture
PM → Architect → Task DAG/Work Queue → 100 dynamic Engineer workers → Continuous QA → Final QA → Verified Delivery. Total 103 logical agents (1 PM + 1 Architect + 100 Engineers + 1 QA). Workers are lightweight coroutines sharing `engine_fn`, NOT 103 full LLM loops. Bounded pool (AIMD 8→100), dependency waves, file-conflict serialization, timeout/retry/checkpoint, work-stealing, task-specific context slices. Live entry: `app/v4/wiring.py:get_team103/run_team103` + `MultiAgentOrchestrator.run_team103`. 20 opts in `app/v4/` (22 files incl. `__init__`+`wiring`), scheduler `app/team103/scheduler.py` (185L).

## 3. Benchmark weakness root causes
O=85.0: 4-role serial pipeline, 4x LLM amplification, no fan-out. 192.6s slowest: serial planner+roles+full verify+sync log+cold index (1346.9ms @566 files/6168 symbols) + static prompt rebuild per turn. C9 audits: cold cost paid inline, no prefetch. A=88.0: whole-run failover, no per-request jittered retry+checkpoint. H4=6.5: no streaming parser (aggregate-then-parse) + nudger round-trips. Evidence: sync writes on hot path. Browser: `cleanup()` exists but no pool/atexit/sweeper. Exploration: repeated lookups, no semantic cache. Planning/verify: regenerate + full suite per edit. Details: `docs/v4/POSTMORTEM.md`.

## 4. Optimizations implemented (20)
OPT-1 prefix_cache · OPT-2 semantic_cache · OPT-3 async_dag · OPT-4 parallel_tools (DAG-aware dispatch) · OPT-5 stream_parser · OPT-6 speculative · OPT-7 prefetch · OPT-8 memory_tiers (L1-L4) · OPT-9 intel_memory · OPT-10 context_mgmt · OPT-11 model_router · OPT-12 plan_cache · OPT-13 risk_verify · OPT-14 recovery (JSON repair/retry/checkpoint) · OPT-15 browser_pool · OPT-16 async_log · OPT-17 dedup · OPT-18 merger · OPT-19 cont_qa · OPT-20 roles. All bound live via `app/v4/wiring.py` (single additive/lazy/reversible point) into toolcall/orchestrator/base/planner/verification/code_search/browser/memory/llm/streaming.

## 5. Per-optimization latency saved (this run)
- OPT-7+cache: cold 1346.9ms → warm 45.9ms (−1301ms/audit)
- OPT-3/4: 5×10ms serial 50.6ms → parallel 10.3ms (4.9x)
- OPT-1: 1000 prefix builds 0.80ms (0.0008ms/hit, 999 hits)
- OPT-16: 500 events+flush 3.6ms (no hot-path stall)
- OPT-8: write100 2.35ms / read100 0.06ms (RAM hot path)
- OPT-10: 100KB→~3KB in 4.9ms with `truncated` marker contract kept
- OPT-5: 2-chunk parse 0.04ms, no full-response wait
- OPT-2: 200/200 hits in 33.87ms (saves LLM+search round-trips; needs index-backed sim at scale)
- OPT-15: fleet stability (no per-task ms; prevents collapse)
- OPT-12/13: plan regen + full-verify minutes saved on low-risk edits (risk tiers)

## 6. Baseline vs optimized latency
| Stage | Optimized (this run) | Baseline/prior | Delta |
|---|---|---|---|
| index walk (257 files) | 2.7ms | 2.6–3.14ms | stable |
| intel COLD | 1346.9ms (566f/6168sym) | 860.7ms (262f) | tree grew; cost now off critical path via prefetch |
| intel WARM | 45.9ms | 14.6ms | fast-path holds; saves ~1.3s/audit |
| sqlite100 | 0.27ms | 0.10–0.17ms | stable |
| tiered w100/r100 | 2.35/0.06ms | 2.46/0.05ms | stable |
| summarize 100KB | 4.9ms | 18.6ms | faster (smaller excerpts) |
| prefix 1000 | 0.80ms | 0.76ms | stable |
| semcache 200 | 33.87ms | 2.36ms | slower (difflib scan) — functional win, perf debt noted |
| DAG 5×10ms | 10.3ms (4.9x vs serial) | same | holds |
| log 500 | 3.6ms | 2.4ms | stable |
| stream parse | 0.04ms | 0.04ms | stable |
| Team103 10/25/50/75/100 | 13/13/20/20/23ms | 10–20ms | stable, peak 8/17/28/43/68 |

## 7. Throughput improvement
DAG fan-out 4.9x on 5-way; Team103 100 tasks in ~23ms harness time (simulated 10ms workers) with AIMD 8→68 peak, no deadlock; read-only tool fan-out (limit 8) removes queue serialization; async log/prefetch remove hot-path stalls.

## 8. Memory improvement
L1/L2 absorb hot state (100 reads 0.06ms), L3 WAL+NORMAL batched (100-row 0.27ms), L4 Markdown durable; per-write sync stalls removed; intelligent memory adds relevance/recency/reliability + contradiction detect.

## 9. Tool-call reduction
Dedup claims + file/symbol locks + result cache (conflict test: 5 same-file → 1 executes); semantic cache 200/200 hits; plan cache kills regen; speculative prep overlaps safe reads.

## 10. LLM-call reduction
Prefix reuse (999/1000 hits) + semantic hits + plan cache + routing (fast vs strong, benchmark consistency locked to bailu-2.8-free) + streaming dispatch (no extra round-trips) + H4 JSON repair (no nudger retries).

## 11. Cache hit rate
prefix 999/1000; semcache 200/200 (threshold 0.5, ctx-scoped); plan cache keyed (goal+hint+fingerprint); intel warm 566 skipped/0 changed; tiered L1 absorbs 100/100.

## 12. Parallel execution gain
`run_dag` == `gather` on fan-out (10.3ms), 4.9x vs serial; Team103 waves preserve `parent→child` order; conflict serialization + work-stealing keep scaling linear to 100.

## 13. 100-worker stress result
`tests/v4/test_team103_stress.py` 7 passed (10/25/50/75/100 + conflict + crash): 13/13/20/20/23ms, peak 8/17/28/43/68, avg_conf >0.5, no deadlock (<60s gate), crash isolated, duplicates skipped. `tests/v4/` total 31 passed in ~1s.

## 14. Recovery improvement
`repair_json` + jittered `retry_async` + `Checkpoint` + `WorkerSupervisor.run_guarded` live in `toolcall.py:532` (H4 path); Team103 retry recovers flaky-once; crash test: boom+good → 2 results, error contained, DAG continues.

## 15. Browser cleanup result
`BrowserPool` (max 4, idle TTL 120s, `atexit._sync_sweep`, `sweep_idle`, exhausted guard) wired in `browser_use_tool.py:42`; orphans bounded, no unbounded growth.

## 16. Memory accuracy improvement
Intelligent memory classification + triple-score retrieval + contradiction detection; context_mgmt keeps errors/symbols excerpts + artifact refs (source-of-truth re-retrievable); cap marker `truncated` contract fixed (75ae8d6) so model re-fetches instead of assuming.

## 17. Test result
`tests/v4/`: **31 passed**. Full suite: **683 passed, 1 failed, 2 skipped** — sole failure pre-existing on clean tree (`TestSkillsRuntime::test_relevant_skill_selected_for_task`, verified via stash-free clean check), v4 introduces zero regressions.

## 18. Regression result
v4 slice green; full-suite delta = 0 new failures; OPT-10 marker fix re-verified (`truncated` in output, head/tail preserved); live wiring imports additive/lazy (no import-time side effects).

## 19. Remaining weaknesses
- semcache difflib scan 33ms/200 — needs index-backed similarity.
- Cold index still 1.3s on 566 files — prefetch hides but doesn't shrink parse; need incremental AST + watch.
- Provider failover still whole-run; per-request jittered retry wired only for tools, not LLM path.
- LLM TTFT/reasoning not measured here (no live LLM runs; harness pins bailu-2.8-free, metrics via `app/llm/metrics.py`).
- QA gate `qa_passed=False` on synthetic specs (no real files) — expected; live QA needs real changed-file existence.

## 20. Next optimization priorities
1. Index-backed semantic similarity + incremental indexer (kill 33ms scan + shrink 1.3s cold).
2. Per-request LLM retry/failover with checkpoint (close A=88 gap).
3. Risk-tier auto-tuning from historical verify outcomes (close Q/L).
4. Streaming parser deeper into `llm.py` (not just toolcall boundary) for H4.
5. Team103 real-LLM engine + work-stealing telemetry + 100-worker live-LLM stress for <120s→<90s validation.
