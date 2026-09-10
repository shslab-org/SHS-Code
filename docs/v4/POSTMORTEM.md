# v4.0 Benchmark Post-Mortem (measured, source-first)

## Baselines
- Brief authoritative (1700-scale, A–Q): SHS v3.1.0 1636.0/1700 (96.2%), rank #2 behind OpenHands 1655.5 (97.4%). Slowest harness avg ~192.6s/task.
- Repo Compare/ (250-scale, 2026-09-06): SHS v3.1.0 single 149/250 (59.6%) rank #1; multi 78/250; OpenCode/OpenHands 74/250; Hermes 57/250.
- Local pytest baseline (this run): 652 passed, 1 failed, 2 skipped. Pre-existing failure: `tests/test_deep_subsystems.py::TestSkillsRuntime::test_relevant_skill_selected_for_task`.

## Weakness → Root cause (source-verified)
1. O=85.0 multi-agent/orchestration, O8 time-cap: `app/agent/orchestrator.py` runs 4-role pipeline serially via dependency events; every role = full LLM loop (`app/agent/roles/*.py` → `BaseRole.run` → LLM + tools). No worker pool, no DAG fan-out, triage only splits simple/small/complex. Request amplification 4x under shared RPM cap.
2. Avg 192.6s slowest: serial pipeline (planner LLM call + 4 roles + full verification + sync logging + cold index refresh 1346.9ms re-measured this run at 566 files/6168 symbols, prior 860.7ms at 262 files + repeated static prompt rebuild in `app/llm/message.py` + `app/agent/base.py` identity+directives rebuilt per turn).
3. C9 long audits wall-clock: `IntelligenceCache.refresh()` cold 1346.9ms / warm 45.9ms re-measured this run (prior 860ms/14ms on smaller tree) — but no background prefetch; audits pay cold cost inline. `walk_source_files` + parse inline on critical path.
4. A=88.0 provider fallback/state: `app/llm/fallback.py` + `rate_limiter.py` + `credential_pool.py` exist but failover is whole-run, no per-request jittered retry with state checkpoint; session resume gaps fixed partially in v3.1.
5. H4=6.5 malformed tool-output recovery: `app/agent/toolcall.py` narration/plan-gate nudgers add extra LLM round-trips on malformed JSON; no incremental streaming parser (`app/llm/streaming.py` aggregates then parses).
6. Evidence pipeline complexity: `app/observability/logging_utils.py` + `metrics.py` + `event_log.py` sync writes on hot path; stdout evidence missing → extra complexity.
7. Chromium leftovers: `app/tool/browser_use_tool.py` has `cleanup()` but no guaranteed hook (no atexit/orphan sweeper, unbounded pool, no timeout kill).
8. Deep exploration latency: `app/intelligence/search.py` + `cache.py` + `code_search.py` repeat same lookups per role with no semantic cache, no invalidation-aware reuse.
9. Planning/verification overhead: `app/planner.py` regenerates plans; `app/verification.py` runs full suites per edit, no risk tiers.
10. Weak cats O(85.0) A(88.0) Q(92.0) L(94.5) G(95.5) map to orchestration, fallback, QA-gating, planning, context respectively. Strengths B/I/K/P/D/F/N must not regress.

## Targets
- <120s avg/task first, then <90s, without disabling verification/exploration/planning/tests/evidence (no theater).
