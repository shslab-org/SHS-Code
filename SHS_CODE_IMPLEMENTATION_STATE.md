# SHS Code Phase 2 State

## Repository
- Source: github.com/shslab-org/ManusClaw (working copy: /home/z/my-project/SHS-Code)
- Language: Python 3.11+ (tested 3.12), package `app/`, 340+ files
- Product: **SHS Code v2.0.0** (SHS Lab — Sazzad Hussain Shobuj)
- Phase 1 (v1.0.0, commit 63b726d) fully preserved — nothing rewritten, only extended

## Current Phase
Phase 2 COMPLETE — Claude Code-level coding intelligence upgrade. 342 tests passing.

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
- 98 new tests across 6 files (342 total: 244 Phase 1 preserved + 98 Phase 2)

## Tests Passed
342 passed, 2 skipped (pre-existing skips) — full suite green

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
Full test suite green (342 passed); REPL smoke test of all new commands.

## Last Failed Action
(none outstanding)

## Next Action
Commit v2.0.0 + push to origin/main.

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
