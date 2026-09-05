# SHS Code State — v3.1.0 (Forensic-Perfection Round)

## Repository
- Source: github.com/shslab-org/SHS-Code (working copy: /home/z/my-project/SHS-Code)
- Language: Python 3.11+ (tested 3.12), package `app/`, 340+ files
- Product: **SHS Code v3.1.0** (SHS Lab — Sazzad Hussain Shobuj)
- Version single-source: app/__init__.py `__version__` — CLI / server
  /healthz / installer banner / pyproject all derive from it

## Current Phase
FORENSIC-PERFECTION ROUND COMPLETE — driven by the Compare/ benchmark
evidence (memory recall failure, context window overflow, multi-agent
amplification, leak noise) plus a 4-subsystem deep audit (memory, context
window, multi-agent orchestration, resource leaks). ~46 findings fixed,
37 new regression tests, LIVE NIM matrix 9/9. Suite: 653 passed, 0 failed.

## v3.1.0 — What was fixed (by subsystem)

### Memory (benchmark task-01/02/05 root causes)
1. `Memory._trim` pinned ALL system messages → long REPL sessions evicted
   the ENTIRE dialogue. Now: first+last system kept, counted against the
   budget; ordering preserved.
2. One-shot turn-2 amnesia: continuity was opt-in (--session/--continue).
   Now: one-shot AUTO-CONTINUES the most recent session (<=30 min, not
   running). LIVE: "remember 91" → new process → "what was the number?"
   → "91".
3. LongTermMemory: WAL + busy_timeout=5000 + synchronous=NORMAL (was
   default DELETE journal; SQLITE_BUSY silently dropped stores/recalls);
   delete() now runs under the lock (was bypassing it); FTS replace now
   delete-then-insert (INSERT OR REPLACE left phantom tokens forever);
   close() actually called from BaseAgent.cleanup() (was dead code — one
   leaked SQLite connection per agent).
4. LTM stores distilled TOOL facts (numbers/paths/outcomes) + goal +
   narration — tool outputs were never persisted, which is why in-session
   recall failed; recall cap 220 → 800 chars/hit; progress checkpoints
   deduplicated.
5. `latest_session()` prefers interrupted/finished/error over 'running'
   (could attach a session live in another process).
6. User message write awaited directly (was fire-and-forget — a kill lost
   the turn-1 row, so turn-2 replayed nothing).
7. MEMORY.md/USER.md (layer 3) injected into context at run start (bounded
   head, replaced in place) — previously nothing ever read them.
8. /resume journal continuity: run() preserves a pre-set _journal_task_id
   and _plan_graph (used to task_start a NEW row — resumed task stayed
   in_progress forever, plan-gate saw an empty DAG).
9. History replay truncation 800 → 4000 chars (final answers persist 4000).

### Context window
10. Tool outputs capped at history insertion (12k head+tail, env-tunable)
    — bash/python/view were explicitly untruncated; one `cat` of a big
    file permanently consumed the window and ballooned every request.
    Full output still journalled.
11. AUTO-COMPACTION: pre-request token guard (90% of config
    [context].max_tokens — now actually wired, was dead config) + retry-once
    after a context-overflow API error (was a dead-end run error).
    TokenLimitExceeded detection unified across provider paths.
12. System prompt injected ONCE per agent (was re-added every run: REPL
    sessions accumulated ~10.3KB duplicated system content per turn, all
    pinned by _trim). Mode/profile directives now REPLACE in place.
13. Tool-intelligence hint boxes REPLACED per step (were additive — a
    30-step run re-sent 29 stale ranking boxes). [CONTEXT REFRESH] and
    [PLAN STATUS REFRESH] also replace in place.
14. Chat mode skips plan injection entirely (a heuristic DAG +
    IMPLEMENTATION PLAN system message used to pollute pure Q&A).
15. Compaction prefix table aligned with the ACTUAL injected formats
    (mismatch classified injections as "user requirements").
16. Anthropic/Google conversions merge ALL system messages (Anthropic kept
    only the first; Google last-wins — a plan refresh overwrote the whole
    system prompt). This was the silent context loss on provider switch.
17. Memory token-guard: token-based eviction of oldest body messages with
    pair integrity (max_context_tokens, wired from config).

### Multi-agent (benchmark: 55/250, rank 5)
18. Message-bus publish-before-subscribe race FIXED: roles now subscribe
    BEFORE awaiting upstream deps — every direct artefact handoff
    (PM→Architect→Engineer→QA) used to be silently DROPPED (the
    "Input does not appear to be a design document" root cause chain).
19. Handoff truncation [:3000] → head+tail at 24k (the Architect's
    IMPLEMENTATION PLAN is the LAST section — the prefix cut deleted
    exactly what the Engineer needed).
20. `on_stage_error` hook stored (was accepted but never stored →
    AttributeError crashed the whole pipeline on ANY role failure —
    observed in benchmark traces task-22/task-25).
21. Upstream ERROR no longer flows downstream (QA used to 'validate' the
    Engineer's error text; downstream stages of a failed dep are SKIPPED).
22. Failure fallback: engineer-stage failure/timeout now falls back to the
    single-agent path (bounded 300s) — was a total loss.
23. --session honored on the complex path (was overwritten unconditionally).
24. Orchestrator mode propagated to Engineer/QA sub-agents (was hardcoded
    BUILD — plan-mode approval gating silently bypassed); delegate tool
    inherits the parent's mode via the run context.
25. Request amplification cut: Engineer/QA sub-agents skip the LLM planner
    (_force_heuristic_plan — the Architect's [TASK-N] design is already in
    the prompt; the duplicated planner call cost a full ~30s request slot,
    the #1 timeout driver). Engineer retry CONTINUES the same session
    instead of a fresh agent redoing work.
26. Triage: long pure QUESTIONS (>25 words, no artifact/file intent) route
    to simple Q&A (PM used to write a PRD for an explanation request);
    Hinglish question starters recognized.

### Resource leaks (the "Event loop is closed" noise + real leaks)
27. node_execute/data_viz timeout: process killed + reaped (were orphaned
    forever with unclosed transports).
28. MCP failed connect: spawned server process killed via BaseException
    cleanup (was one orphan per agent run on a flaky server);
    disconnect() escalates terminate→kill and closes pipe transports.
29. GGUF models: module-level cache (was one FULL model load per agent —
    OOM under load); cleanup_backend releases it.
30. run()'s protected region starts before skill injection (cancellation
    there used to leak Bash shell, browser, MCP clients, DB connections).
31. Fire-and-forget cleanup tasks strongly referenced (router + gateway —
    asyncio weak refs could GC them mid-cleanup, leaking everything).
32. SDK backends (OpenAI/Anthropic) got cleanup(); rotated-key one-off
    clients closed after every call (httpx pools were never closed).
33. Bash atexit: one module-level weak-tracked handler (was a STRONG-ref
    handler per Bash instance — unbounded registry growth in server
    processes); reset on generic exception + CancelledError (output
    mixing between commands fixed).
34. Parallel executor timeout force-releases the abandoned thread's
    resource locks (thread-ownership checks made normal release refuse —
    deadlock-by-timeout); force_release_write/read added to the RW lock.
35. python_execute: cancelled join terminates the worker process (server
    cancellation used to orphan the worker for weeks).
36. Canvas sessions LRU-capped at max_sessions (grew unboundedly);
    intelligence manager closes evicted cache connections.
37. cron scheduler job.id → job.job_id (AttributeError crashed the
    scheduler on the first due job).
38. Rate limiter: clock-jump clamp (mixed/future timestamps could demand
    a 155s+ wait — hung the suite on freshly booted machines).

## LIVE Verification Matrix (v3.1.0, real NVIDIA NIM)
- Normal Hinglish chat: natural reply, "Bhai, main theek hoon, aap kaise
  ho?" — 1 request, 3s ✓
- Simple math: 15% of 240 → "36 (240 × 0.15)" ✓
- **Auto-continue turn-2 recall: "remember 91" → NEW process → "91" ✓
  (the benchmark task-01 killer)**
- Agent work any-directory: fib.py created + run + externally verified
  fib(10)=55 ✓
- Multi-agent triage: "2+2?" → direct answer 3s, APPROVED ✓
- Full suite: 653 passed, 2 skipped, 0 failed ✓

## Environment Note (2026-09-05)
NVIDIA NIM tightened minimaxai/minimax-m3 to ~1-burst + 10-15s recovery
(~4-6 RPM, was ~10 RPM at the v1 benchmark). All agents' benchmark
scores are environment-bound; SHS single-agent ranks #1 (80/250) in the
re-run under the harshest conditions — most resilient under 429 pressure.
gpt-oss-120b/qwen3-coder-480b/deepseek-v4-flash: EOL (410).
gpt-oss-20b: healthy (tool calling + 8/8 burst capacity) — now default.
Any-directory setups: ~/.shscode/.env needs LLM_API_KEY + LLM_BASE_URL +
LLM_MODEL (all three).

---

# HISTORICAL STATE (v3.0.3 — preserved)

## v3.0.3 Commits (this phase)
- 71a80a1 v3.0.3 UX round — 7 live-found fixes: EOL default model
  (gpt-oss-120b 410 → gpt-oss-20b), console_level WARNING (DEBUG spam
  gone from terminal), LLM_MODEL env var + loud 404 warning, actionable
  404/401 LLM errors, cwd-scoped last_interrupted() (stale-task leak),
  chat-mode directive (last-position system msg — natural chat in any
  language), /help corrupted line fixed
- 711bc38 v3.0.3+ identity — single version source of truth; banner
  /healthz/index.html/installers/CODE_OF_CONDUCT/SECURITY swept clean
  of the old 5.1.1/The-JDdev identity
- 18d1964 v3.0.3+ gate integrity — terminate-tool goal-completion bypass
  CLOSED (same gate as text answers); task_dag active-deps auto-complete
  (no more "ERROR: cannot complete" noise in final answers); explicit
  _max_steps no longer overridden by mode scaling
- 95c9ae1 docs — README What's New v3.0.3 + badges

## LIVE Verification Matrix (v3.0.3, real NVIDIA NIM)
- Normal chat EN: "Hi! How are you?" → natural reply, 1 request, clean ✓
- Normal chat Hinglish: "Bhai kaise ho? mausam batao" → Hinglish reply,
  follow-up question, ZERO files created ✓
- Conversation continuity: "Raj/7" stored → new process --session recalls ✓
- Simple math: 15% of 240 → "36" with math shown, 1 request ✓
- Agent work any-directory: fib.py created+run+verified (55) ✓
- Complex agent work: calculator project (calc.py + 13 pytest tests
  all passing) with clean verified final summary ✓
- Multi-agent triage: "2+2?" → simple → direct answer 4.3s ✓
- Model switch: --model minimaxai/minimax-m3 → "42" ✓
- Server: /healthz 3.0.3, /run/sync "four", async /run "Paris",
  sessions/messages reflect real state ✓
- Interrupt/resume: 12-module task → 12/12 functionally verified ✓
- Rate limit resilience: 6/6 minimax-m3 requests absorbed through
  adaptive limiter (429s paced, state preserved) ✓
- CLI command sweep: 50/50 ✓
- Full suite: 613 passed, 2 skipped, 0 failed ✓

## Environment Note (2026-09-05)
NVIDIA NIM tightened minimaxai/minimax-m3 to ~1-burst + 10-15s recovery
(~4-6 RPM, was ~10 RPM at the v1 benchmark). All agents' benchmark
scores are environment-bound; SHS single-agent ranks #1 (80/250) in the
re-run under the harshest conditions — most resilient under 429 pressure.
gpt-oss-120b/qwen3-coder-480b/deepseek-v4-flash: EOL (410).
gpt-oss-20b: healthy (tool calling + 8/8 burst capacity) — now default.

---

# HISTORICAL STATE (v2.1.0 and earlier — preserved)


## Repository
- Source: github.com/shslab-org/ManusClaw (working copy: /home/z/my-project/SHS-Code)
- Language: Python 3.11+ (tested 3.12), package `app/`, 340+ files
- Product: **SHS Code v2.1.0** (SHS Lab — Sazzad Hussain Shobuj)
- Phase 1 (v1.0.0, 63b726d) + Phase 2 (v2.0.0, bc9bd5a) fully preserved —
  nothing rewritten, only extended and stabilized

## Current Phase
STABILIZATION COMPLETE — 6 known bugs + 40+ audit findings fixed; live
NVIDIA NIM validation matrix green; 489 regression tests passing.

## Stabilization Commits
- c1a0fa9 v2.1.0-stabil1 — 6 known bugs + 7 audit findings (427 tests)
- 8be0895 v2.1.0-stabil2 — 30+ bugs from triple-subsystem audit (469 tests)
- ccb2ba1 v2.1.0-stabil3 — 4 more live-NIM bugs + live 40-RPM verification
- 8e2872d v2.1.0-stabil4 — any-directory universal + narration guard
- 9dc8219 v2.1.0-stabil5 — goal-completion gate (spec §34)

## Bugs Found & Fixed (stabil3–stabil5, all LIVE findings on real NIM)
1. FINAL-ANSWER SEMANTICS: text-only response (no tool calls) never ended
   the loop — only "task complete" phrases did. Direct answers ("NIM_LIVE_OK",
   "42") looped, tripped the duplicate nudge, terminated WITHOUT returning
   the answer. Fixed in ToolCallAgent.act(): no-tool-calls + non-empty
   assistant content = final answer (standard function-calling protocol).
2. NARRATION GUARD: mid-tier models narrate their next action as text
   ("I'll create the test file next") instead of emitting the tool call;
   strict final-answer semantics ended runs with work half-done. Bounded
   nudge (5) with narrow first-person forward-intent patterns.
3. GOAL-COMPLETION GATE (spec §34): models summarise PARTIAL progress as
   final answers ("f1.py and f2.py created") while the plan has pending
   steps — journal recorded 'completed' with the goal objectively
   incomplete. Gate: text answers only end the run when the journaled DAG
   (reloaded from journal, reflecting task_dag tool updates) has no
   pending/ready/active/blocked steps; applies only once work started
   (tool_call_count > 0) so pure Q&A answers stand; budget 3.
   LIVE RESULT: long task 2/10 files -> 10/10 (70 steps, 73 requests).
4. ANY-DIRECTORY UNIVERSAL: agent in a directory without project
   config.toml silently fell to MockLLM with LLM_BASE_URL+key exported.
   _detect_provider() now maps LLM_BASE_URL -> universal; key chain accepts
   NVIDIA_API_KEY.
5. CONFIG LAYER SHADOWING: partial ~/.manusclaw/config.yaml (mcp_servers: [])
   shadowed the ENTIRE project config.toml (provider -> mock). Layers now
   deep-merge: project < home.toml < home.yaml < profile.
6. BASH HEREDOC HANG: '(cmd); echo' broke heredoc commands ('PY);' invalid
   terminator) -> hang until deadline. Newline-separated wrap.
7. LLM.backend_info() len(_pool.credentials) TypeError -> _pool.size.

## LIVE NVIDIA NIM Validation Matrix (real API, real key, 40 RPM)
- one-shot direct answer: 1 step, answer returned, clean exit, 0 leak warnings
- 45-request burst: 0 errors / 0 429s; #41 waited exactly window-slide
  (37.0s after 23.5s of requests) — true rolling window, no naive sleeps;
  NIM auto-detect = 40 RPM; NO artificial 4 RPM anywhere (4 exists only as
  a tiny unit-test window)
- Live E2E workloads 10/10 (W1 simple coding, W2 terminal+report, W3
  multi-file lib+tests, W4 debug broken.py, W5 codebase exploration — all
  externally verified by running the produced files)
- Live server lifecycle 11/11 (run/sync, async /run, /sessions reality:
  state/step_count/messages/timestamps, no stale running sessions,
  malformed-request handling)
- Live model switch + resume 7/7 (interrupt mid-work -> switch
  gpt-oss-120b -> gpt-oss-20b -> resume, no duplicate work)
- Live long task across 40-RPM boundary: 10/10 files, 70 steps, 158s,
  73 requests, goal-completion gate fired once and drove completion
- CLI command sweep: 50/50 commands against the real dispatcher

## Architecture Audit
Pre-audit of Phase 1 found 20 gaps (all listed in git history of this file);
ALL closed in Phase 2. Phase 1 systems were EXTENDED, never replaced:
Journal extended in place (schema migration adds columns/tables), ToolSelector
gained persistent confidence, LLMMetrics-wired health added alongside.

## Completed (Phase 2, by spec section)
- [x] §2-§4  Project Intelligence Layer: app/intelligence/ — Python AST indexing,
      JS/TS/Kotlin/Java/PHP/Go structural parsing, symbol+import tables,
      semantic concept search (auth→login/jwt/token expansion), structural
      (usages/callers/importers) search, filename/text/regex search
- [x] §3     Persistent incremental cache: ~/.manusclaw/intel/<hash>/index.db,
      mtime+size keyed — reindex ONLY changed files (verified: 2nd pass 0 changed,
      partial refresh 1 file); post-edit incremental refresh wired into agent
- [x] §6-§8  Task DAG: app/task_dag.py — task_nodes table, statuses
      pending/ready/active/completed/failed/retryable/skipped/blocked,
      dependency-enforced completion (refused until deps done), smart
      prioritization (unlock-value > user priority > fewer failures > age),
      persistence + reload, /plan rendering, plan-in-context injection
- [x] §7     Smart planning: app/planner.py — LLM plan (validated+repaired JSON)
      with heuristic fallback; plan persisted, MERGED not lost on task change
- [x] §9     Work State 2.0: journal columns plan/phase/decisions/test_results/
      recovery_actions/blocked_reason/verification (idempotent ALTER migration)
- [x] §10-11 Exact resume: verify_resume_state() — filesystem vs checkpoint
      comparison, claimed-but-missing detection, changed-since detection,
      already-done detection (symbol index backed duplicate-work prevention);
      wired into /resume output + injected into restored context
- [x] §12    IDE-like editing: precise-edit guidance + post-edit index refresh
- [x] §13    Review phase: automatic self-review prompt every 3 file edits
- [x] §14-17 Verification engine + failure recovery: app/verification.py —
      project-aware command selection (python/node/android/gradle/php/rust/go),
      bounded execution, error extraction (pytest/TS/gradle/npm/php patterns),
      DIAGNOSE→hypothesis→fix analysis; app/recovery.py — 12-class error
      classification + strategy (RETRYABLE/WAIT_AND_RETRY/REQUIRES_FIX/
      REQUIRES_USER/EXTERNAL_BLOCKER), retry-after extraction, repeated-failure
      strategy change (§17)
- [x] §18    Tool confidence persists ACROSS runs (~/.manusclaw/tool_confidence.json,
      decayed 50% per run) — extends in-run ToolSelector scoring
- [x] §19    Parallel tool execution: all-read-only batches run concurrently
      (asyncio.gather), mutating ops stay strictly sequential
- [x] §20-21 Provider health: app/provider_health.py — per-provider requests/
      errors/rate-limit/latency-EMA/tokens/cost, 🟢🟡🔴 status, cooldown,
      recommend_provider() routing hint; wired into LLM._call_with_retry
- [x] §22    Model switching state preservation: verified end-to-end (E2E test 06)
- [x] §23    Context compaction 2.0: app/compaction.py — structured extraction
      (requirements/facts/decisions/files/changes/errors/tests/task-state/plan),
      verbatim tail preserved; /compact→/compress upgraded
- [x] §24    /usage: provider table (req/err/rate/latency/in/out/cost) + session
      token usage
- [x] §25-26 Multi-agent + subagent state: delegate tool records start/finish/
      interruption in subagents table (journal.db); recovery on /resume
- [x] §27    Sessions: switch/rename/archive/delete added (SessionDB extended,
      archived sessions hidden from default list)
- [x] §28    Project profiles: intelligence profile persisted
      (~/.manusclaw/intel/<hash>/profile.json)
- [x] §29    Environment intelligence: app/intelligence/environment.py — 50+ tool
      detections with versions, /env, command_available() pre-check
- [x] §31    Git intelligence 2.0: app/git_intel.py — full state (branch/dirty/
      staged/untracked/diff/conflicts/merge/ahead-behind/history), commit
      existence VERIFIED (never claimed), /git upgraded
- [x] §32    GitHub workflow: git_providers + connectors preserved (Phase 1)
- [x] §33    Smart rollback: app/git_intel.py SmartRollback — pre-edit snapshots
      of agent-touched files (~/.manusclaw/rollback/<task>/), restore touches
      ONLY snapshotted files; /rollback command
- [x] §34    Dependency intelligence: dependency files/lockfile detection in profile
- [x] §35    Skills 2.0: levels builtin/user/project/installed, /skill install
      (path or git URL), create, remove; project skills from .shscode/skills/
- [x] §36    Agent modes: app/modes.py — coding/debugging/reviewer/research/
      autonomous/planning; each changes plan depth, verification level,
      step budget, tool bias, injected directive; persisted (/mode)
- [x] §37    Custom profiles: app/agent_profiles.py — system instructions +
      skills + preferred tools + model pref + verification strategy,
      5 builtin examples, CRUD + activation (/profile)
- [x] §38    Secret isolation: mask in health errors, providers, connectors (Phase 1
      secret_redaction preserved); E2E-verified
- [x] §39-43 Observability: ActivityBus events for indexing/plan/verifying/
      parallel/review/rollback/subagent/blocked; /status 2.0 (progress %, phase,
      files, tests, verify verdict, blocked reason, next action, health line);
      /doctor 2.0 (Phase 2 subsystem checks)
- [x] §44-45 Error classification + retry intelligence: recovery.diagnose()
      wired into tool retry loop (REQUIRES_USER → BLOCKED not fail; §47
      human-dependency: journal.set_blocked with reason/needed/next_action)
- [x] §46-47 Long-running autonomy + human-dependency detection
- [x] §48    Agent handoff: this ledger + journal + checkpoints + plan (E2E verified)
- [x] §49-55 TESTS: tests/test_integration_e2e.py — the 17-scenario suite +
      model switch (§51) + provider failure (§52) + 4 RPM rate limit (§53) +
      interruption (§54) + crash recovery (§55, atomic persistence verified) +
      parallel tools + 400-file repo performance (index < 20s, incremental < 1s)
- [x] §57-58 Terminal UX: new activity lines, stable input preserved (Phase 1 fix)
- [x] §62-63 Documentation + this ledger

## In Progress
(none)

## Files Created (Phase 2)
- app/intelligence/{__init__,indexer,cache,search,project,environment,manager}.py
- app/task_dag.py, app/planner.py, app/verification.py, app/recovery.py
- app/git_intel.py, app/provider_health.py, app/compaction.py
- app/modes.py, app/agent_profiles.py, app/subagents.py
- app/tool/{code_search,project_intel,verify,task_dag_tool}.py
- tests/{test_intelligence,test_task_dag,test_planner,test_verification,
  test_phase2_systems,test_integration_e2e}.py

## Files Modified (Phase 2)
- app/state.py — DAG table + Work State 2.0 columns + full JSON deserialization
- app/agent/base.py — project-context + plan injection, mode/profile application,
  plan refresh, blocked-on-user final verdict
- app/agent/toolcall.py — parallel read-only batches, error classification gate,
  pre-edit snapshots, post-edit index refresh, file-edit counter
- app/agent/manus.py — 4 new tools wired, review phase, CODE INTELLIGENCE +
  RECOVERY directives, delegate/task refs
- app/llm/llm.py — provider health + usage recording in call path
- app/cli.py — /plan /verify /project /env /usage /mode /profile /rollback +
  /status 2.0 /doctor 2.0 /resume exact-verification /compress structured /
  /git 2.0 /skills levels /skill install|create|remove /sessions extended +
  activity feed events
- app/skills/skill_engine.py — levels, project skills, install/remove
- app/tool/selector.py — cross-run persisted confidence
- app/tool/delegate.py — subagent state recording
- app/db/session.py — rename/archive/delete + archived filtering

## Bugs Found & Fixed during Phase 2
1. modes.py/agent_profiles.py had import-time path constants → call-time lazy
   (test isolation + runtime home switching)
2. intelligence INTEL_ROOT same issue → _intel_root()
3. Journal.get_task/current_status didn't deserialize new JSON columns → fixed
4. JS import regex missed default imports (import X from "y") → fixed
5. Kotlin fun regex mis-captured receiver-less functions → fixed
6. compaction decision regex missed "Decision:" (trailing \b after colon) → fixed
7. provider_health recommend matched provider+model key only → provider-level
8. verification emit() kind kwarg collision → renamed
9. rate limiter fake-clock/real-clock mixing in tests → monotonic + short window
10. ScriptedLLM planner probe consumed agent script → separate ask() path

## Tests Added
- Phase 2: 98 tests across 6 files
- Stabilization: test_stabilization_fixes.py (84 from stabil1/2) + 23 from
  stabil3-5 (final-answer semantics, narration guard, goal-completion gate,
  config deep-merge, any-directory detection, heredoc, pool_size)

## Tests Passed
489 passed, 0 failed — full suite green

## Performance Findings
- Own repo (337 files): full index 1.0s, incremental refresh ~0ms
- 400-file synthetic repo: index < 1s, 2nd pass < 1s, symbol search < 0.5s
- /verify fast on this repo: 0.5s (compileall)

## Provider State
MockLLM in test env; universal OpenAI-compat client + custom provider registry
+ health telemetry in production path (wired into _call_with_retry).

## Model State
Model switch verified state-preserving (E2E test_06); LLM remains replaceable.

## Memory State
LongTermMemory recall/store preserved (Phase 1) + recalled into context.

## Work State
Journal + Task DAG + Work State 2.0 columns + subagents table, all persisted.

## Current Blockers
(none)

## Last Successful Action
Full suite 489/489 green; LIVE NIM matrix green (E2E 10/10,
server 11/11, switch+resume 7/7, long task 4/4, 50-command sweep 50/50);
README updated to product docs for v2.1.0; version bumped.

## Last Failed Action
(none outstanding)

## Next Action
Commit v2.1.0 (stabil5 + docs) and push to origin/main.

## Architecture Decisions
1. EXTEND, never replace: Journal schema migration (ALTER + CREATE IF NOT EXISTS)
   instead of new state store — zero data migration, zero parallel systems.
2. Deterministic intelligence: AST/regex/SQL-based symbol+semantic search — no
   embedding model required; concept expansion covers "where is auth handled"
   style queries with zero external dependencies.
3. Read-only parallelism only: mutating operations never parallelize (spec §19).
4. Error intelligence as a gate: classification decides retry vs fix vs user
   BEFORE burning retries (spec §45), and REQUIRES_USER → task BLOCKED, never lost.
5. Fake features forbidden: every command/tool has a real execution path; all
   claims verified by the E2E suite on a real temp filesystem + git repo.
