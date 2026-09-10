# v4.0 Full Repository Exploration Inventory (source-first, spec PHASE 1)

Measured 2026-09-10, host shs-code-live, branch main, version 4.0.0.
Method: source code first — no doc-based assumptions. Every entry verified by `ls` + `grep` + `sed` on live tree.

## Tree top (`app/`)
activity.py, agent/, agent_profiles.py, automation/, canvas/, cli.py, compaction.py, config.py,
connectors/, context/, conversation/, cron.py, db/, desktop/, doctor.py, env.py, events/,
exceptions.py, file_store/, flow/, git_intel.py, git_providers/, hooks/, integrations/,
intelligence/, llm/, logger.py, mcp/, memory/, messaging/, migrations/, modes.py,
multi_agent.py, nodes/, observability/, parallel_executor/, permissions/, planner.py,
provider_health.py, providers.py, recovery.py, sandbox/, schema.py, secrets/, security/,
server/, session_tools.py, skills/, ssh/, ssh_server.py, state.py, subagents.py,
task_dag.py, task_queue.py, team103/, tool/ (25 tools), v4/ (22 files), verification.py, voice/

## Subsystem → actual location
- agent core loop: `app/agent/base.py` (1236 lines, BaseAgent, system-inject-once, protected region) + `app/agent/react.py` + `app/agent/shscode.py`
- planner: `app/planner.py` (376 lines: llm_plan + generate_plan + verify_resume_state + already_done_check)
- executor: `app/agent/toolcall.py` (839 lines: JSON parse at :519, read-only parallel batch)
- tool system: `app/tool/` (25 tools) — base `app/tool/base.py`
- tool registry: `app/tool/__init__.py`
- tool execution pipeline: `app/agent/toolcall.py::_execute_with_retry` + `_run_one` + selector
- model/provider: `app/llm/llm.py` (1143 lines, UniversalClient + LLM router) + `app/providers.py` + `app/llm/litellm_client.py`, `bedrock_client.py`, `mistral_client.py`, `credential_pool.py`, `fallback.py`, `rate_limiter.py`, `retry.py`, `offline_router.py`, `profile_rotation.py`
- streaming: `app/llm/streaming.py` (852 lines, aggregates then parses — no incremental tool-call dispatch)
- context management: `app/agent/context.py` + `app/compaction.py` + `app/llm/message.py` (647 lines, EnhancedMessage)
- memory: `app/memory/` (long_term.py, short_term.py) + `app/tool/memory_tool.py` + `app/db/session.py`
- SQLite layer: `app/db/session.py` + `app/intelligence/cache.py` (WAL+NORMAL) + `workspace/.sessions/shscode.db`
- Markdown memory: `workspace/.memory/` + `app/memory/long_term.py`
- work notebook: `workspace/` + `app/file_store/`
- task journal: `app/state.py:122 Journal` + `checkpoint()` at :434
- task DAG: `app/task_dag.py` + `app/tool/task_dag_tool.py` + `app/flow/planning.py`
- task queue: `app/task_queue.py` (TaskCheckpoint at :57)
- worker pool: `app/task_queue.py` + `app/parallel_executor/executor.py` + `resource_lock.py`, `declared_resources.py`
- checkpoint: `app/state.py:checkpoint` + `app/task_queue.py:TaskCheckpoint` + `app/v4/recovery.py:Checkpoint`
- recovery: `app/recovery.py` + `app/db/session.py:recover_stale_sessions` + `app/v4/recovery.py`
- retry: `app/llm/retry.py` + `app/llm/fallback.py`
- context compaction: `app/compaction.py` + `app/agent/context.py`
- code search: `app/tool/code_search.py` (66 lines) → `app/intelligence/search.py` + `cache.py`
- AST indexer: `app/intelligence/indexer.py` + `cache.py:refresh()` (cold 860.7ms / warm 14.6ms measured)
- semantic search: `app/intelligence/search.py` (concept expansion map, _tokens, expand_query)
- project_intel: `app/tool/project_intel.py` → `app/intelligence/` (manager.py, project.py, cache.py, search.py)
- browser: `app/tool/browser_use_tool.py` (124 lines, cleanup() at :114 but no atexit/pool — OPT-15 gap)
- MCP: `app/agent/mcp.py` + `app/mcp/`
- skill engine: `app/skills/skill_engine.py` + `app/tool/skill_manager.py` + `app/skills/builtin/`
- delegation: `app/tool/delegate.py` + `app/subagents.py` + `app/conversation/`
- parallel executor: `app/parallel_executor/executor.py` + `app/agent/toolcall.py` parallel read-only batch
- multi-agent orchestration: `app/agent/orchestrator.py` (4-role serial pipeline) + `app/multi_agent.py` + `app/agent/roles/` + `app/team103/scheduler.py` (185 lines, Team103)
- verification gates: `app/verification.py` (312 lines, VerificationEngine.verify) + `app/tool/verify.py`
- completion gates: `app/agent/toolcall.py::_terminate_blocked_by_plan_gate`
- plan gates: `app/planner.py` + `app/task_dag.py`
- session/resume: `app/db/session.py` + `app/session_tools.py` + `app/planner.py:verify_resume_state`
- configuration: `app/config.py` (headless=True at :106) + `~/.shscode/config.yaml`
- never_confirm/headless: `app/config.py:106 headless` + `app/cli.py:1543 headless/visible`
- logging: `app/logger.py` + `app/observability/logging_utils.py` (533 lines, sync JSON) + `app/activity.py`
- observability: `app/observability/` (correlation.py, health.py, logging_utils.py, metrics.py, tracing.py) + `app/llm/metrics.py`
- tests: `tests/*.py` (39 files) + `tests/v4/` (3 files, 27 tests)
- benchmarks: `Compare/` (results.md, scores.json, scores_table.md, methodology.md, harness/, shs-code/, shs-offline/) — no `benchmarks/` dir; authoritative numbers in handoff brief (1700-scale)
- performance-sensitive paths: `app/intelligence/cache.py:refresh`, `app/agent/base.py:301 sys_content`, `app/llm/message.py`, `app/agent/toolcall.py:519 json.loads`, `app/verification.py:verify`, `app/observability/logging_utils.py`, `app/tool/browser_use_tool.py`

## v4 layer (existing, isolated)
`app/v4/` 22 files = 20 opts + `__init__.py` + `wiring.py` (184 lines). `app/team103/scheduler.py` 185 lines.
GAP (this run): zero imports of `app.v4` / `app.team103` outside `app/v4/`, `app/team103/`, `tests/v4/` — wiring.py exists but no live caller. This is the wiring work for PHASE 6-10.

## Counts
- app/agent/base.py 1236, toolcall.py 839, verification.py 312, planner.py 376, streaming.py 852, message.py 647, llm.py 1143, code_search.py 66, intel cache.py 379, logging_utils.py 533, browser_use_tool.py 124. Total hot-path 6507 lines.
- tools: 25. tests: 39 + v4 3. v4 modules: 22.
