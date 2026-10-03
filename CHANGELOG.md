# Changelog

All notable changes to **ManusClaw** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
---

## [4.3.0] — 2026-10-04

### Summary

v4.3.0 fixes the four problem classes found during the real
SHS-Code + Agnes test run: the **max_steps configuration bug** (a
user-configured 80 was silently ignored), the **background execution
lifecycle** (background agent processes died with the surrounding
session), a **tool-call error on resumed sessions**, and the
**GitHub contributor attribution requirement** — now enforced
mechanically and non-bypassably.

### max_steps — user-controlled, never silently replaced

- **Root cause fixed**: the shipped example `config.toml` placed
  `max_steps` (and `workspace_dir`) inside `[logging]` — TOML section
  placement silently swallowed them (pydantic `extra='ignore'`), so the
  runtime kept the default 30. The example file is corrected AND the
  loader now performs strict schema-placement validation: a top-level
  setting found inside any section is a hard, actionable `ConfigError`
  ("move it above the section header"). Unknown keys only warn;
  `SHSCODE_CONFIG_PERMISSIVE=1` downgrades hard errors for legacy files.
- **Three more silent-replacement bugs fixed**: the server
  `RunRequest.max_steps` defaulted to a hardcoded 30 (every GUI/API run
  stomped the configured value — now `None` = "use the configured
  value"); `local/remote_conversation` fell back to hardcoded 30 (now
  the shared resolution layer); mode scaling's `max(5, …)` floor turned
  a configured 3 into 5 (mode scaling now applies only to the unset
  default budget, never to a user-chosen value).
- **User control surfaces**: CLI `--max-steps N`, GUI Agent-panel
  "Steps" box (per run), GUI Settings "Agent Step Budget"
  (`POST /config/max-steps`, persisted 0600), env `SHSCODE_MAX_STEPS`,
  top-level `max_steps` in any config layer. Precedence:
  explicit selection > env > profile > home > project config > default.
- **Transparency**: the effective value + its source layer are shown at
  every surface (CLI `/config`, run-start log line, `GET /config`,
  GUI Settings) — the runtime can never again silently disagree with
  what the user supplied.

### GitHub attribution — mandatory, non-bypassable

- Every git commit created inside SHS Code (agent bash sessions, GUI
  terminal, GitHub panel, runtime paths) is attributed to
  **SHS-Code-Agent** `<SHS-Code-Agent@users.noreply.github.com>` as
  author AND committer, plus the Co-Authored-By trailer.
- **New git shim** (`~/.shscode/shims/git`, first on the PATH of every
  SHS-Code child process) mechanically strips `--author`/`--reset-author`
  from `git commit` and forces the four identity env vars on
  commit-creating commands — prompt-level, flag-level (`git -c
  user.email=…`), and env-level (`env -u GIT_AUTHOR_…`) bypass attempts
  are all defeated. The user's own shells outside SHS Code and their
  git configuration are untouched.
- **All opt-outs removed**: `SHSCODE_AGENT_IDENTITY=0` no longer exists;
  `apply_agent_git_env` always overwrites inherited identity variables;
  `GitHubProvider.commit(credit_agent=False)` is ignored. The system
  prompt carries the attribution mandate and instructs the agent to
  explain (not obey) "commit as me" requests.
- **Contributors-system fact** (verified empirically): GitHub's
  contributor aggregation counts USER and BOT accounts only — the
  SHS-Code-Agent profile is currently an Organization and organizations
  do not appear in the Contributors list (commits still link to the
  profile everywhere). The noreply address is forward-compatible: if a
  USER account named `SHS-Code-Agent` is ever registered, the exact
  same attribution starts counting toward contributors with zero code
  changes.

### Detached execution lifecycle

- `SHSCode --detach "<task>"`: double-fork + `setsid` daemon — survives
  the terminal, SSH disconnect, and process-tree cleanup of the tool
  that started it. Registry under `~/.shscode/runs/<run_id>/`
  (`run.json` + `output.log`), live status via `SHSCode --runs`,
  log streaming via `SHSCode --attach <run_id>`.
- `POST /run {"detach": true}` + GUI Agent-panel "detached" checkbox:
  long tasks run as their own OS process and survive server restarts;
  the Sessions panel shows the detached-run registry with liveness.
- SIGTERM/SIGHUP now cancel the run **gracefully** — the agent
  checkpoints and closes the session as `interrupted`
  (`--continue` / `/resume` restore it; nothing is silently lost).

### Resumed-session tool-call error — root cause fixed

- OpenAI-compatible providers (Agnes) reject any request whose history
  contains an assistant `tool_calls` block without matching `tool`
  results (HTTP 400). Two real paths produced that state: a run
  **cancelled mid-tool** (CancelledError bypassed the result append)
  and an **EXTERNAL_BLOCKER early return** that skipped the append.
  Both producers now always append the tool result; in addition
  `sanitize_tool_history()` enforces the protocol invariant at the LLM
  request boundary regardless of how the memory was produced
  (interruption, restore, compaction, replay).
- Tool failures now record structured diagnostics (`tool name`,
  `exception class`, `args preview`, `tool_call_id`) in the log and a
  `tool_failure_diagnostic` activity event — enough to debug and
  recover without guessing.

### Preserved

- The Agnes/API rate-limit retry/recovery behavior is untouched and
  fully guarded by the existing test suite (all green).

---
---

## [4.2.0] — 2026-10-03

### Summary

v4.2.0 delivers the four follow-up mission items: a **workspace
diff-viewer in the GUI**, a **pytest CI workflow**, **every messaging
stub completed** (Discord, Slack, Teams, Google Chat, Email), and the
**SHS-Code-Agent identity enforced everywhere** — every commit, push,
co-author and contributor attribution, from both CLI and GUI.

### Added
- **Workspace diff-viewer** (GUI Workspace panel): a *Changes* tab next
  to *Files* — per-file status badges (M/A/D/N), +adds/−dels stats,
  summary chips, line-numbered colorized unified diffs
  (green added / red removed / blue hunks), and three comparison modes:
  *Working tree* / *Staged* / *vs HEAD*. Served by the new
  `GET /workspace/diff` endpoint (untracked files synthesized as
  new-file diffs; graceful outside a git repo).
- **CI pytest workflow** (`.github/workflows/tests.yml`): full suite on
  Python 3.11 + 3.12 for every push/PR to main. The Pylint workflow
  matrix was also fixed (it still targeted 3.8–3.10 while
  `requires-python >= 3.11` — it could never install the package).
- **Messaging adapters completed** (no stubs remain):
  - *Discord*: real Gateway websocket protocol — HELLO/heartbeat,
    IDENTIFY with intents, RESUME with session+seq, reconnect backoff,
    MESSAGE_CREATE dispatch, REST send chunked to 2000 chars.
  - *Slack*: real Socket Mode — `apps.connections.open` with the
    app-level token, envelope ACKs, message-event dispatch, reconnect
    with backoff; send-only mode when only `SLACK_BOT_TOKEN` is set.
  - *Teams*: Bot Framework OAuth2 client-credentials token (cached),
    activity send to the right regional `serviceUrl`, and inbound
    activity parsing.
  - *Google Chat*: service-account RS256 JWT (signed via `cryptography`)
    exchanged for an access token, plus the **send-URL bug fix** (the
    old code POSTed to the literal `{space}` placeholder and always
    404'd) and inbound event parsing.
  - *Email*: IMAP polling loop (UNSEEN search → RFC822 fetch → parse →
    dispatch → mark seen) with configurable interval.
  - New messaging webhook routes: `GET/POST
    /messaging/webhooks/whatsapp`, `POST /messaging/webhooks/teams`,
    `POST /messaging/webhooks/google-chat`, `GET /messaging/channels`.
- **SHS-Code-Agent identity everywhere** ("sab jagah" rule):
  `GitHubProvider.commit()` now forces **author + committer** to
  `SHS-Code-Agent <SHS-Code-Agent@users.noreply.github.com>` via
  per-command `-c` overrides (the user's git config is never touched),
  keeps the `Co-Authored-By` trailer and `Generated with SHS-Code`
  footer, and reports the effective author; `pull()` merge commits are
  attributed the same way; CLI and server startup export
  `GIT_AUTHOR_*` / `GIT_COMMITTER_*` so agent bash sessions and the
  GUI terminal panel commit as the agent too. Opt-out:
  `SHSCODE_AGENT_IDENTITY=0`.

### Fixed
- Deleted files were missing from the workspace diff (the unified-diff
  parser only read paths from `+++ b/` headers; it now also handles
  `--- a/` + `+++ /dev/null`).
- Pylint CI matrix mismatch (see above).

### Tests
- `tests/test_v420_features.py` — 50 new regression tests: agent
  identity (real-repo commit authorship, env export, opt-out),
  `/workspace/diff` (all modes, untracked synthesis, summary math,
  parser units), GUI diff-viewer static pins, CI workflow pins, Discord
  gateway protocol (identify/resume/heartbeat/dispatch), Slack socket
  mode (ack + dispatch + bot filtering), Teams OAuth + send + webhook,
  Google Chat JWT signature verification + URL interpolation + webhook,
  Email IMAP poll, and the messaging webhook routes.
- Suite: 776 → 826 collected (823 passed, 3 documented environmental
  skips).

---
---

## [4.1.0] — 2026-10-03

### Summary

v4.1.0 is a **GUI usability release**: the requested collapsible navigation
(slide/hide sidebar), a beginner-friendly GUI guide (in-app Help panel +
`docs/GUI_GUIDE.md`), and one real bug found in the QA panel.

### Added

- **Collapsible sidebar (slide/hide navigation)** — the whole nav slides
  off-canvas with an animated transition. Three toggle paths: the ☰ top-bar
  button, the `☰ MENU` edge tab (visible while hidden), and
  `Ctrl`/`Cmd`+`B`. Preference persists via `localStorage`
  (`shs-gui-nav-hidden`). Below 820px the sidebar becomes an overlay drawer:
  closed by default, backdrop + `Esc` close, auto-close after picking a panel.
- **Help / Guide panel (14th GUI panel)** — plain-language quick-start
  (first task in 3 steps), one-line panel reference for all 14 panels,
  navigation help, chat-vs-activity explanation, task status legend,
  keyboard shortcuts, troubleshooting, and CLI↔GUI relationship. No
  programming knowledge assumed.
- **`docs/GUI_GUIDE.md`** — 15-chapter complete guide for normal users:
  layout, nav slide, first task walkthrough, every panel explained, honest
  finish reasons, statuses, Git/GitHub safety, data locations,
  troubleshooting, FAQ, CLI↔GUI cheat sheet. Mirrored to shs-code-docs.
- **`tests/test_gui_nav_v410.py`** — 19 regression tests pinning the toggle
  button, edge tab, transition CSS, keyboard binding, persistence key,
  mobile drawer mode, backdrop/Esc close, drawer auto-close, Help panel
  content, and the QA-badge boolean fix.

### Fixed

- **QA panel status badge always rendered `unknown`** — the JS compared
  `rep.ok === True` (a Python literal leaked into browser JavaScript, where
  `True` is undefined). Now a real boolean comparison. Found during the
  v4.1.0 GUI audit.

### Version

- 4.0.1 → 4.1.0 (`app/__init__.py`, `pyproject.toml`, README, CHANGELOG).
- Test suite: 776 collected, all green.

---

## [4.0.0] — 2026-09-10

### Summary

v4.0.0 is a **latency + architecture release**: 20 measured optimizations
plus a 103-agent team architecture (1 PM + 1 Architect + 100 dynamic
Engineer workers + 1 QA). Version bumped 3.1.0 → 4.0.0 across
`app/__init__.py`, `pyproject.toml`, CLI, server, and README (single source).

### Added

- **`app/v4/`** — 20 optimization modules: prefix_cache, semantic_cache,
  async_dag, stream_parser, speculative, prefetch, memory_tiers,
  intel_memory, context_mgmt, metrics, model_router, plan_cache,
  risk_verify, recovery, browser_pool, async_log, dedup, merger,
  cont_qa, roles.
- **`app/team103/`** — Team103 scheduler: PM decompose, Architect waves,
  bounded worker pool (8→100 AIMD), dependency waves, file-conflict
  serialization, timeout/retry/checkpoint, work-stealing, QA gate.
- **`tests/v4/`** — 27 tests: optimization correctness, 10/25/50/75/100
  worker stress, conflict serialization, crash recovery, phase ordering.
- **`docs/v4/`** — POSTMORTEM.md (measured baselines + root causes),
  LATENCY_PROFILE.md (re-verified this run: cold 860.7ms / warm 14.6ms /
  sqlite 0.10ms / tiered write 2.46ms / read 0.05ms / DAG 4.9x / log 2.4ms).
- **`app/v4/wiring.py`** — production wiring: single additive/lazy/reversible
  import point binding all 20 opts into the live agent (caches, prefetcher,
  router, plan cache, event log, risk tiers, JSON repair, context summarize +
  live Team103 entry (`get_team103`/`run_team103`) + `MultiAgentOrchestrator.run_team103`).

### Changed

- Bumped version `3.1.0` → `4.0.0` (single source `app/__init__.py`).
- README: version badge + v4.0.0 feature block.

### Verification

- `tests/v4/`: **31 passed**.
- Full suite spot-check: pre-existing failure only
  (`tests/test_deep_subsystems.py::TestSkillsRuntime::test_relevant_skill_selected_for_task`);
  v4 introduces no regressions.


## [5.1.1] — 2026-06-20

### Summary

v5.1.1 is a **maintenance / bug-fix release** that closes 32 bugs discovered
in v5.1.0 across the agent core, security layer, FastAPI server, cron
scheduler, secrets redaction, multi-agent role pipeline, and observability
subsystem.

All fixes are covered by the existing test suite plus two new regression
tests; the full suite runs **212 passed, 2 skipped, 0 failed** (was 210
passed, 2 failed in v5.1.0). Static-analysis coverage of F821 (undefined
names) and F841 (unused-but-assigned locals) is now **0 errors** (was 23).

### Added

- **Regression tests** for the webhook router route-ordering bug
  (`tests/test_webhooks.py`):
  - `test_webhook_router_create_endpoint_not_swallowed_by_catchall` —
    POSTs to `/webhooks/create` via the real FastAPI `TestClient` and
    asserts `200` (was `404` before the route-order fix).
  - `test_webhook_router_trigger_still_works_after_reorder` — ensures
    the parameterised `POST /webhooks/{hook_id}` route still triggers
    webhooks with non-literal IDs after the reorder.
- **Changelog section in README.md** (`## 🔧 What's Fixed in v5.1.1`)
  with a tabular breakdown of every fix.
- **This file** (`CHANGELOG.md`) — first formal release audit trail.

### Changed

- Bumped version `5.1.0` → `5.1.1` in:
  - `pyproject.toml`
  - `app/cli.py` (`VERSION` constant and the welcome banner string)
  - `app/server/main.py` (FastAPI app `version`, `/healthz` payload,
    lifespan startup log, root endpoint message)
  - `run_server.py` (ASCII-art banner)
  - `build_release.py` (`TAG_NAME` template — was still on `v4.0.0`)
  - `README.md` header, footer, and badges.

### Fixed

#### Critical — runtime crashes / broken endpoints

- **`app/agent/router.py`** — `AgentRegistry._evict_idle` was declared
  `async` but called from sync `get()` / `put()` without `await`, so
  eviction never ran (idle-TTL test expected `None` but got the cached
  agent). Converted `_evict_idle` to a sync method; agent `cleanup()`
  coroutines are now scheduled fire-and-forget via `_safe_create_task`.
  Also fixed the LRU `put()` path that called `move_to_end` but did not
  overwrite the stored agent when re-inserting an existing key.
- **`app/cli.py`** — `logger` was referenced in two functions without
  being imported → `NameError` on the Spinner long-operation exit path
  and the background-task checkpoint-restore path. Fixed with local
  `from app.logger import logger as _logger` imports at the use-site.
- **`app/conversation/stuck_detector.py`** — `_action_fingerprint`
  referenced undefined `tool_call` instead of the local `tool_name` →
  `NameError` on every action without a `.function` attribute, breaking
  stuck detection.
- **`app/integrations/slack.py`** — `re` was used in
  `@self._bolt_app.action(re.compile(...))` but never imported →
  `NameError` on Slack Bolt action-handler registration. Added
  `import re`.
- **`app/server/webhook_router.py`** — **Route ordering bug**:
  `@router.post("/{hook_id}")` was declared before
  `@router.post("/create")`, so FastAPI matched the parameterised path
  first and `POST /webhooks/create` returned `404` ("Webhook 'create'
  not found"). Create / list / delete were all broken via HTTP. Reordered
  the router so literal sub-paths (`/create`, `/sign/{hook_id}`) come
  before the parameterised catch-all, and documented the ordering
  requirement in the module docstring.
- **`app/observability/health.py`** — `LLMHealthChecker._test_api_call`
  was `def` (sync) but called `llm.ask(...)` which is async → returned
  a coroutine object that was silently discarded (F841 `result`). The
  health check would always report success regardless of the LLM's
  actual state. Re-implemented to bridge the sync/async boundary via a
  worker thread running `asyncio.run`. Also fixed the call signature:
  `LLM.ask` takes a list of `Message` objects, not a string.
- **`app/llm/profile_rotation.py`** — `ModelProfile.default()`
  exception fallback called `cls(name="default")` but `__init__` does
  not accept `name` → `TypeError` masked the original error. Construct
  the profile first, then set `.name`.
- **`app/llm/credential_pool.py`** — Forward-reference `"ModelProfile"`
  triggered F821 (undefined name) under strict type checking. Use
  `TYPE_CHECKING` import so the symbol is resolvable for type checkers
  without creating a runtime circular import.
- **`app/observability/metrics.py`** — `Union` was used in three
  module-level type hints but never imported → F821 on module import
  under strict checkers. Added `Union` to the existing `typing` import.
- **`app/voice/talk.py`** — `Any` was used in two instance-variable
  annotations but never imported → F821. Added `Any` to the existing
  `typing` import.

#### Logic & correctness

- **`app/cron.py`** — `_JOBS_FILE = Path(os.getenv(...))` was evaluated
  ONCE at module import. Runtime changes to `MANUSCLAW_CRON_FILE`
  (tests, profile switching, CLI overrides) were silently ignored.
  Replaced with `_get_jobs_file()` lazy resolver called inside
  `_load_jobs` / `_save_jobs`.
- **`app/cron.py`** — `manusclaw-cron --trigger JOB` did not `return`
  after triggering → fell through to `asyncio.run(scheduler.run_forever())`
  and blocked the terminal forever. Added `return`.
- **`app/cron.py`** — `--list` output overwrote `output` on every loop
  iteration (`output = f"{t}"`) instead of appending, so only the LAST
  output_target was ever shown. Use `output += f" {t}"` and strip.
- **`app/skills/skill_engine.py`** — Same module-level-eval bug as
  cron.py: `_SKILLS_DIR` was set at import time and ignored subsequent
  `MANUSCLAW_SKILLS_DIR` changes. Replaced with `_get_skills_dir()`
  lazy resolver; updated `_load_user()` and `create()` to call it.
- **`app/tool/memory_tool.py`** — Same bug: `_WORKSPACE` /
  `MEMORY_FILE` / `USER_FILE` frozen at import. The `tmp_workspace`
  pytest fixture set `MANUSCLAW_WORKSPACE` at runtime, but
  `MemoryTool.execute()` still wrote to the import-time path — tests
  passed only because they manually monkey-patched `mt.MEMORY_FILE`.
  Added `_get_workspace()` / `_memory_file()` / `_user_file()` lazy
  resolvers; rewrote `execute()` to use them.
- **`app/task_queue.py`** — Same bug: `_WORKSPACE` / `_DB_PATH`
  evaluated at import. Added `_get_db_path()` lazy resolver;
  `TaskQueue.__init__` calls it when no explicit path is provided.
- **`app/llm/secret_redaction.py`** — AWS-secret pattern used a
  non-capturing prefix group `(?:secret_key...|aws_secret...)` so
  `redact()` replaced the entire match including the prefix —
  `secret_key=ABC...` became `***REDACTED***` (prefix lost). Converted
  to a capturing group and use the `\1` backreference pattern, matching
  the other redaction rules.
- **`app/integrations/resolver.py`** — `clear_results(older_than_hours=24)`
  computed `cutoff` but never used it — every terminal-status result was
  removed regardless of age, breaking the documented "older than N hours"
  contract. Now uses `started_at` to filter by age, with a safe default
  (keep results we can't prove are old enough).

#### Resource leaks

- **`app/agent/roles/engineer.py`** — `Manus()` instances were created
  for the main pass and the retry pass but `cleanup()` was never called
  → leaked Bash subprocesses (and any other tool resources) for the
  lifetime of the process. Wrapped each Manus run in `try/finally` with
  a `_cleanup_agent` helper.
- **`app/agent/roles/qa.py`** — Same leak as engineer.py: the QA Manus
  agent was never cleaned up. Added `try/finally` with cleanup call.

#### Test pollution

- **`tests/test_voice.py`** — `test_get_tts_provider_returns_nulltts_stub`
  did `tts_mod._create_provider = lambda name: ...` — a permanent
  module-level monkeypatch that leaked into every subsequent test in
  the file, causing `test_get_tts_provider_preferred_openai` to receive
  `NullTTS` instead of `OpenAITTS`. Use the `monkeypatch` fixture so
  the override is automatically restored at test teardown.

#### Dead-code / F841 cleanup

- **`app/canvas/tool.py`** — `_add_chart` captured
  `state = await self._server.update(...)` but never used it. Now
  reports the resulting component count for consistency with the other
  canvas method.
- **`app/file_store/s3.py`** — `write_stream` computed
  `key = self._make_key(path)` but never used it. Removed the
  assignment but kept the call for its path-traversal-validation
  side-effect.
- **`app/conversation/local_conversation.py`** — `_do_fork` computed
  `fork_log_path` but never used it. Now logged at DEBUG level so the
  path is visible in diagnostics.
- **`app/integrations/webhook_handler.py`** —
  `handler_result = await handler(event)` discarded result. Replaced
  with bare `await handler(event)` + explanatory comment.
- **`app/parallel_executor/executor.py`** —
  `call_lookup = {c.call_id: c for c in calls}` built but never used.
  Removed with explanatory comment (results are correlated via `zip()`).
- **`app/llm/litellm_client.py`** — `except Exception as e: ... raise`
  — `e` unused. Dropped the `as e` binding.
- **`app/observability/health.py`** — Two
  `except Exception as e: ... raise` blocks — `e` unused. Dropped the
  `as e` bindings.
- **`app/voice/wake.py`** — `sample_width = 2` assigned but never used.
  Converted to a comment so the int16 / 2-byte intent is preserved for
  future readers porting to other audio libraries.
- **`app/integrations/resolver.py`** — `service` and `content` bindings
  unused in the `apply_changes` path. Removed bindings with explanatory
  comments noting why the calls are still made (validation side-effect).

### Security

No new CVE-class vulnerabilities were introduced or fixed in this
release. The existing security controls were audited as part of the
bug-fix pass:

- **Path-traversal protection** in `LocalFileStore._resolve()` was tested
  against `../../../etc/passwd`, `/etc/passwd`, `a/../../b`, `../outside`,
  `subdir/../../../etc/passwd` — all blocked with
  `FileStorePermissionError`.
- **Command-injection surface** in `Bash` / `DockerSandbox` /
  `OpenShellSandbox` was audited — all use `asyncio.create_subprocess_exec`
  (no shell), so no shell-metacharacter injection is possible at the
  transport layer. Catastrophic-command blocking remains at the regex
  layer in `app/permissions/gate.py` and `app/tool/bash.py`.
- **Secret redaction** regex set was hardened (see logic fix above) so
  context prefixes (`secret_key=`, `aws_secret=`) are preserved when
  redacting the secret value.

### Verification

- `pytest` → **212 passed, 2 skipped, 0 failed** (was 210 passed,
  2 failed in v5.1.0).
- `ruff check app/ --select F821,F841` → **0 errors** (was 23).
- FastAPI `TestClient` HTTP smoke test against `/healthz`, `/`,
  `/tools`, `/sessions`, `/webhooks` (create / list / trigger-with-HMAC /
  delete) — all pass.
- Module import audit — all 133 main modules import cleanly under
  Python 3.12.
- Path-traversal audit — see Security section above.

---

## [5.1.0] — 2026 (prior release)

Enterprise-grade enhancement release. See the `## 🆕 What's New in v5.1`
section in [README.md](README.md) for the feature highlights, and the
`911fc1e` / `6a0b7f7` commits on `main` for the implementation history.

---

## Maintenance Policy

- **Patch releases** (`5.1.x`) — bug fixes, regression tests, and
  security hardening only. No new features, no breaking API changes.
- **Minor releases** (`5.x.0`) — new features, optional dependency
  additions, and backward-compatible API extensions.
- **Major releases** (`6.0.0`) — breaking API changes; will be
  accompanied by a migration guide.

To report a bug or request a backport, open an issue at
<https://github.com/ManusAgents/ManusClaw/issues> and tag it with
`bug` + the affected version.
