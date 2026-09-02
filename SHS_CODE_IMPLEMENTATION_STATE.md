# SHS Code Implementation State

## Repository
- Source: github.com/shslab-org/ManusClaw (working copy: /home/z/my-project/SHS-Code)
- Language: Python 3.11+ (tested 3.12), package `app/`, 300+ files
- Product: **SHS Code v1.0.0** (SHS Lab — Sazzad Hussain Shobuj)
- Predecessor: ManusClaw v5.1.1 (fully preserved, `manusclaw` command alias kept)

## Current Phase
COMPLETE — all 24 phases implemented and verified. 244 tests passing.

## Completed
- [x] Phase 1-2: Full repository audit (2 parallel deep audits + manual core reads)
- [x] Phase 3: Existing bugs fixed (see Bugs Fixed)
- [x] Phase 4: SHS Code branding + SHSCode CLI + ASCII banner + `exit` keyword
- [x] Phase 5: Provider-independent state layer (app/state.py: Journal + StateStore, SQLite + atomic JSON)
- [x] Phase 6: Memory system wired (LongTermMemory: recall at run start, store at run end, /memory /remember /forget + delete method)
- [x] Phase 7: Task journal + checkpoints (every tool exec → record_action + file/command tracking + atomic checkpoint)
- [x] Phase 8: Provider-independent context (messages live in agent memory, never in LLM layer)
- [x] Phase 9: LLM.switch() live rebuild (model/provider/base_url/key; token budget object preserved)
- [x] Phase 10: NVIDIA NIM rolling-window limiter (app/llm/rate_limiter.py; NIM auto-detect 40 RPM; Retry-After honored; blocked_until for 429 pressure; /status shows stats)
- [x] Phase 11: Failure recovery (retry loop never mutates messages; RateLimitError carries retry_after; journal checkpoints survive crashes)
- [x] Phase 12: Full command system (37 commands, all real — smoke tested)
- [x] Phase 13-14: 29 builtin skills + enable/disable persisted (~/.manusclaw/skills_state.json) + /skill info|enable|disable|reload
- [x] Phase 15: Custom providers (app/providers.py registry, ~/.manusclaw/providers.json, /provider add/remove/set-key/switch, masked display)
- [x] Phase 16: MCP fixed (initialize handshake, notifications/initialized, stderr drain task, notification-skip in _rpc, /mcp add/remove/inspect)
- [x] Phase 17: Connectors (app/connectors.py, ~/.manusclaw/connectors.json, masked display, git-provider token injection in BaseAgent init)
- [x] Phase 18: Channels preserved (12 adapters, /channels introspection)
- [x] Phase 19: Tool execution integration (journal wired into ToolCallAgent._execute_with_retry; ActivityBus emissions)
- [x] Phase 20: Terminal UX (live activity feed via ActivityBus: thinking/tools/rate-limit/checkpoint lines; WordCompleter regex bug FIXED; Ctrl+C cancels run not shell; plain `exit`; SPAWN_TASK sentinel fixed; --no-color implemented)
- [x] Phase 21: /doctor diagnostics (11 checks with actionable hints)
- [x] Phase 22: Integration tests (32 new tests: rate limiter / model switch / journal recovery)
- [x] Phase 23: Interruption recovery test (full cycle: run → checkpoint → crash → mark_interrupted → last_interrupted → /resume → context restored)
- [x] Phase 24: Final verification (244 tests pass; REPL smoke tested end-to-end)

## In Progress
(none)

## Pending
- [ ] git push to GitHub (needs credentials in this environment — local commits done)
- [ ] Optional future: EventLog default tempdir (conversation subsystem — not used by main path), Alembic schema consolidation (documented, unused by runtime)

## Files Modified
- app/cli.py — FULL REWRITE (SHS Code shell, 37 commands, activity feed, resume, model switch)
- app/llm/llm.py — rate limiter integration, Retry-After capture, LLM.switch()/switch_sync()/backend_info(), cleanup_backend
- app/agent/base.py — journal wiring, LongTermMemory recall/store, connector injection, step checkpoints, SHS identity
- app/agent/toolcall.py — _journal_tool_execution + activity emissions
- app/agent/manus.py, react.py, toolcall.py, roles/base_role.py, identity_guard.py — identity rebrand
- app/config.py — LLMRateLimitConfig, active_config_path(), save_llm() persistence
- app/skills/skill_engine.py — is_disabled/set_disabled/reload (persisted)
- app/memory/long_term.py — delete() method
- app/mcp/client.py — initialize handshake, stderr drain, notification skip
- app/logger.py — recent_lines()
- main.py — routes to REPL (no more demo-task fallback)
- pyproject.toml — shscode v1.0.0, SHSCode/shscode/manusclaw scripts, rich+prompt_toolkit deps
- requirements.txt — rich, prompt_toolkit added
- install.sh — SHSCode launcher + manusclaw alias → app.cli
- README.md — SHS Code header + quickstart

## Files Created
- app/activity.py (ActivityBus — live UX pub/sub)
- app/llm/rate_limiter.py (RollingWindowRateLimiter + registry + NIM detect)
- app/state.py (Journal + StateStore — persistent state layer)
- app/connectors.py (ConnectorRegistry + mask_token + git-provider injection)
- app/providers.py (ProviderRegistry + KNOWN_MODELS + provider_overlay)
- app/doctor.py (11 diagnostic checks + formatter)
- app/skills/builtin/ — 23 new skills (web-dev, android, python, js, ts, kotlin, java, c, cpp, csharp, php, sql, git, testing, debugging, linux, docs, ui-ux, api, db-eng, security, automation, browser-auto)
- tests/test_rate_limiter.py, tests/test_model_switch.py, tests/test_journal_recovery.py (32 tests)
- SHS_CODE_IMPLEMENTATION_STATE.md (this file)

## Files Removed
(none — preservation principle)

## Existing Features Preserved
- ALL agent classes (BaseAgent/ReActAgent/ToolCallAgent/Manus/MCPAgent/orchestrator/router/roles)
- ALL 14 agent tools + ToolCollection + PermissionGate (BUILD auto-approve behavior unchanged)
- SessionDB, TaskQueue, CronScheduler, EventLog, canvas, voice, sandbox, ssh, desktop, nodes
- 12 messaging channel adapters + gateway + AgentRouter
- GGUF/Ollama/HuggingFace offline routers + universal OpenAI-compat client
- All 212 pre-existing tests still pass (244 total now)
- `manusclaw` command, MANUSCLAW_HOME env, ~/.manusclaw data layout (zero data migration)

## Bugs Found
1. main.py ran a hardcoded demo task on EOF instead of exiting; REPL unreachable from installed command
2. SPAWN_TASK sentinel never handled in CLI loop
3. /model mutated config with NO effect (LLM backend built once)
4. Retry-After header discarded in UniversalClient._post 429 path
5. Naive fixed-60s rate limit wait (not rolling window)
6. LongTermMemory fully built but never instantiated at runtime
7. requirements.txt missing rich/prompt_toolkit (silent REPL degradation)
8. MCP: no initialize handshake, undrained stderr (pipe deadlock risk), single-line response assumption
9. WordCompleter pattern passed as str — crashes completer on every keystroke (input instability, spec §30)
10. --no-color accepted but never implemented
11. /branch could raise unhandled on missing session
12. UniversalClient aiohttp session leak on rebuild (no cleanup path)
13. pyproject "all" extra self-reference typo (`manusclawistral`)

## Bugs Fixed
ALL 13 above fixed (see Files Modified/Created). Also: rate limiter `blocked_until` bug found by test (unlimited limiter ignored Retry-After pressure) — fixed.

## Tests Passed
- tests/test_rate_limiter.py — 15 passed (rolling window semantics, NIM detection, registry, context preservation)
- tests/test_model_switch.py — 8 passed (backend rebuild, budget preservation, agent context survives switch, custom provider overlay+masking)
- tests/test_journal_recovery.py — 9 passed (lifecycle, failure journaling, atomic checkpoints, full interrupt→resume cycle, StateStore, connectors, skills toggles)
- Full existing suite: 244 passed, 2 skipped, 0 failed

## Tests Failed
(none)

## Known Issues
- git push pending credentials (local commits complete)
- EventLog still defaults to tempdir when used via app/conversation (subsystem not on the main agent path; documented)
- Alembic 001 schema remains disconnected from runtime (historical; SessionDB+Journal are the live stores)
- Dead subsystems from ManusClaw (LiteLLMClient, View/Condenser stack, HookManager, security ensemble) intentionally PRESERVED per spec §46 — not removed; wiring them is future work if ever needed

## Current Task
FINAL — verification complete, ready for commit/push

## Last Successful Action
Full test suite green (244 passed); REPL smoke test (banner → /version → /status → /doctor → exit) clean

## Last Failed Action
(none)

## Next Action
git add -A && git commit && git push origin main (needs GitHub credentials in env; work is fully committed locally otherwise)

## Architecture Decisions
- PRESERVE all working ManusClaw systems; extend additively, never delete
- Model switch = rebuild backend only; messages live in agent memory → context can never be destroyed by a switch (spec §4)
- Rate limit wait happens inside LLM._call_with_retry before the request; messages untouched → context survives (spec §19)
- Journal: SQLite (tasks + events) + atomic JSON checkpoints (os.replace, fsync) → crash-safe (spec §43)
- Memory: SQLite FTS5 at workspace/.memory/long_term.db — provider-independent by construction
- Config persistence: ~/.manusclaw/config.yaml (shadows ./config.toml on next load; profile-aware)
- CLI: SHSCode (new) + manusclaw (legacy alias); both → app.cli:main
- Data home unchanged (~/.manusclaw) → zero migration for existing users
- ActivityBus: global pub/sub for live agent activity; UI failures can never propagate into the agent loop

## Provider State
Built-in: mock, openai, anthropic, google/gemini, mistral, bedrock, universal (openai-compat: openrouter/lmstudio/groq/together/perplexity), ollama, gguf, huggingface/hf. Custom registry: ~/.manusclaw/providers.json via /provider add.

## Model State
Default config: provider=mock, model=gpt-4o (safe first-run). Active model switchable live via /model, persisted via Config.save_llm().

## Memory State
LongTermMemory wired into BaseAgent: recall (top-4 FTS hits) injected at run start; goal+outcome stored at run end; /remember /forget manage entries.

## Task State
Journal wired: task_start on run, record_step per step, record_action per tool exec, file/command tracking, checkpoint after every tool + every step + at task end; task_complete only when the loop actually finished (spec §34 — no false completion).

## Recovery Instructions
1. Read this file top-to-bottom (it is the handoff map — spec §49/§50)
2. git log --oneline — see the implementation commits
3. Check "Known Issues" + "Pending" above for remaining work
4. Run: python -m pytest tests/ -o addopts="" — expect 244 passed
5. Run: python -m app.cli — expect SHS Code banner + /help works
6. All integration points are marked with "SHS Code (spec §…)" comments in code
