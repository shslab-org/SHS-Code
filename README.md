<div align="center">

<img src="https://img.shields.io/badge/Version-3.1.0-ff69b4?style=for-the-badge&logo=github&logoColor=white" alt="Version">
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/License-MIT-FFD700?style=for-the-badge&logo=opensourceinitiative&logoColor=black" alt="License">
<img src="https://img.shields.io/badge/Status-Persistent%20%7C%20Autonomous-00C853?style=for-the-badge&logo=bugsnag&logoColor=white" alt="Status">

<br><br>

# ⌨️ S H S &nbsp; C O D E

### **Persistent Autonomous AI Coding Agent — SHS Lab**

**SHS Code** (by Sazzad Hussain Shobuj, SHS Lab) is a persistent, model-independent, autonomous coding agent. It remembers across restarts, switches providers and models **without losing context**, journals every step of every task, checkpoints continuously, and resumes interrupted work automatically.

```text
$ SHSCode
███████╗██╗  ██╗███████╗  ██████╗ ██████╗ ██████╗ ██████╗
██╔════╝██║  ██║██╔════╝ ██╔════╝██╔═══██╗██╔══██╗██╔══██╗
███████╗███████║███████╗ ██║     ██║   ██║██████╔╝██████╔╝
╚════██║██╔══██║╚════██║ ██║     ██║   ██║██╔══██╗██╔═══╝
███████║██║  ██║███████╗ ╚██████╗╚██████╔╝██║  ██║██║
╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝
SHS Code initialized.
```

**What makes SHS Code different:**

| Capability | Meaning |
|---|---|
| 🧠 **Four-layer memory** | SQLite short-term, SQLite long-term, Markdown memory, and an agent work notebook — all survive restarts and model switches |
| ⚡ **Live model switching** | `/model` and `/provider` switch the reasoning backend mid-task — context, files, progress preserved |
| 📓 **Task journal** | Every tool call, file change, command, decision and error is journaled with checkpoints |
| 🔁 **Interruption recovery** | Crash / Ctrl+C / terminal closed → `/resume` continues from the checkpoint without redoing work |
| ⏳ **Rolling-window rate limiting** | Provider defaults (NVIDIA NIM: 40 RPM) with optional custom limits; waits preserve all state |
| 🛠️ **29 builtin skills** | Language/stack skills plus custom skills in `~/.shscode/skills`, per-level enable/disable |
| 🔌 **Custom providers** | `/provider add my-nim openai-compat https://... model key 30` — persisted in the registry |
| 🔎 **Codebase intelligence** | AST-level indexing, semantic + structural search, project profiles |
| 🩺 **`/doctor`** | Full diagnostics with actionable hints |
| 🖥️ **Stable terminal** | Live activity feed (thinking / tools / rate-limit waits), no input flicker |

> ### 🆕 v3.1.0 — Forensic-perfection round: memory, context, multi-agent, leaks
> - **Conversations remember across processes**: one-shot runs now AUTO-CONTINUE the recent session — "remember 91" → new process → "what was the number?" → "91" (the benchmark task-01 killer, fixed).
> - **Context window that protects itself**: tool outputs capped (head+tail, full output still journalled), AUTO-COMPACTION before overflow + retry-once on context errors, system prompts injected once instead of duplicated every turn, ranking/refresh boxes replaced instead of stacked.
> - **Multi-agent that actually passes context**: role artefacts are delivered (bus race fixed), full-fidelity handoffs (24k head+tail instead of a 3k prefix cut), upstream errors skip downstream roles, engineer failure falls back to the single-agent path, sub-agents skip the duplicated planner call, `--session` works on the complex path.
> - **Zero known leaks**: subprocesses killed+reaped on every exit path (node/mcp/bash/python), SQLite long-term memory WAL + closed on cleanup, GGUF models cached once, SDK httpx pools closed, abandoned executor threads force-release their locks, the "Event loop is closed" noise is gone.
> - **Provider-faithful context**: Anthropic/Google now receive ALL system blocks merged (plan/memory/intel directives were silently dropped mid-conversation).
> - **Smarter routing**: long pure questions stay Q&A (no PRD for "explain relativity"), Hinglish questions included.

> ### v3.0.3 — Natural conversation, clean terminal, honest completion
> - **Chat stays chat**: casual conversation (any language) gets a natural one-request reply — no planner, no skill cards, no random file creation. Real tasks still get the full PLAN→ACT→VERIFY pipeline.
> - **Clean terminal**: internal diagnostics (tool scoring, retry internals) go to the log file, not your screen. `console_level` config if you want them back.
> - **Honest completion**: the `terminate` tool is now gated by the same goal-completion check as text answers — "all done" claims with unfinished plan steps are rejected and the agent keeps working.
> - **Works from any directory**: `~/.shscode/.env` (LLM_API_KEY / LLM_BASE_URL / LLM_MODEL) powers the CLI everywhere; 404s and auth failures tell you exactly what to fix.
> - **One version number**: CLI, server `/healthz`, installer banner and `pyproject.toml` all read a single source of truth.

<p>
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows%20%7C%20Docker-informational?style=flat-square" alt="Platforms">
  &nbsp;•&nbsp;
  <img src="https://img.shields.io/badge/Providers-100%2B-FF6F00?style=flat-square&logo=brain&logoColor=white" alt="LLM Providers">
  &nbsp;•&nbsp;
  <img src="https://img.shields.io/badge/Offline-GGUF%20%7C%20HF%20%7C%20Ollama-9C27B0?style=flat-square" alt="Offline">
  &nbsp;•&nbsp;
  <img src="https://img.shields.io/badge/Channels-13-00B4D8?style=flat-square&logo=message&logoColor=white" alt="Channels">
  &nbsp;•&nbsp;
  <img src="https://img.shields.io/badge/Tools-17-00C853?style=flat-square" alt="Tools">
  &nbsp;•&nbsp;
  <img src="https://img.shields.io/badge/Tests-653%20passed-brightgreen?style=flat-square" alt="Tests">
</p>

</div>

## Table of Contents

- [What is SHS Code](#what-is-shs-code)
- [Features](#features)
- [How SHS Code Works](#how-shs-code-works)
- [Autonomous Coding](#autonomous-coding)
- [Persistent Memory](#persistent-memory)
- [Persistent Work State](#persistent-work-state)
- [Checkpoints & Recovery](#checkpoints--recovery)
- [Model & Provider System](#model--provider-system)
- [Rate-Limit Handling](#rate-limit-handling)
- [Tools](#tools)
- [Skills](#skills)
- [MCP](#mcp)
- [Git & GitHub](#git--github)
- [Browser / Web](#browser--web)
- [Multi-Agent System](#multi-agent-system)
- [Server & API](#server--api)
- [CLI](#cli)
- [Channels & Connectors](#channels--connectors)
- [Sandboxing](#sandboxing)
- [Configuration](#configuration)
- [Installation](#installation)
- [Usage](#usage)
- [Examples](#examples)
- [Architecture](#architecture)
- [Testing](#testing)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## What is SHS Code

SHS Code is a terminal-first autonomous coding agent. You give it a goal — "fix the failing login tests", "add pagination to the orders API", "explore this codebase and explain the auth flow" — and it plans, executes, verifies, and reports back, using real tools: a shell, a file editor, a browser, web search, Git, and more.

The defining design principle: **the LLM is a replaceable reasoning engine; SHS Code's state is not owned by it.** Conversations, memories, task journals, checkpoints, file changes and progress live in SHS Code's own persistence layer (SQLite + Markdown + atomic checkpoint files). Switch the model, switch the provider, restart the process, hit a rate limit, lose the network mid-task — the work state survives and the agent continues.

SHS Code runs as an interactive CLI shell (`SHSCode`), a one-shot command (`shscode "do something"`), an HTTP/WebSocket server with a built-in web chat, and as a daemon connected to 13 messaging channels. It supports every major LLM provider plus any OpenAI-compatible endpoint, local GGUF/HF/Ollama models, and a user-defined provider registry.

## Features

**Autonomy & coding**
- PAORR execution loop (Plan → Act → Observe → Reflect → Retry) with self-check every 3 steps and a code review phase every 3 file edits
- Task DAG planning with dependency-enforced completion; completion is refused until dependencies are done
- Project intelligence: incremental AST indexer (Python, JS/TS, Kotlin, Java, PHP, Go), semantic + structural search, project profiles, environment detection
- Verification engine: project-aware build/test command selection, error extraction, failure hypotheses
- Recovery engine: 12-class error classification with per-class retry strategies
- Smart rollback: snapshots of agent-touched files with one-command restore

**Persistence & recovery**
- Four independent memory layers (see [Persistent Memory](#persistent-memory))
- Task journal recording every action, file change, command, decision, test result
- Atomic checkpoints after every meaningful operation; automatic resume after interruption
- Stale-session recovery, interrupted-task detection at startup

**Model & provider independence**
- Live `/model` + `/provider` switching without context loss
- Provider registry with per-provider custom rate limits
- Credential pools with rotation, provider health tracking (🟢🟡🔴), fallback and failover
- Rolling-window rate limiter with provider defaults (no artificial throttling below the limit)

**Integration surface**
- 13 messaging channels, 5 Git forge providers, MCP client + server, webhooks, cron
- Browser automation (Playwright), web search, URL extraction
- Docker / SSH / local sandboxes; S3 / GCS / local file stores
- Observability: structured logging with trace/correlation IDs, health checks, OpenTelemetry-style tracing

## How SHS Code Works

1. **Understand** — the task is classified (Q&A vs. build), and the project intelligence layer is consulted: indexed symbols, architecture map, Git state, environment. Duplicate-work prevention starts here.
2. **Plan** — non-trivial tasks get a persisted, numbered plan (LLM or heuristic planner) stored as a task DAG in the journal. Steps are marked started/completed as work proceeds; completion is dependency-enforced.
3. **Act** — the agent calls tools: edit files, run commands, search the codebase, browse, delegate to subagents.
4. **Observe** — tool output is read carefully; findings are journaled (actions, file changes, commands, discoveries).
5. **Verify** — before any claim of completion, the verification engine runs project-appropriate build/test commands and checks results. A goal-completion gate reloads the journaled DAG and blocks premature "done" claims while steps are pending.
6. **Recover** — failures are classified (12 error classes), retried with matching strategies, or escalated; every recovery is journaled.

Under all of this sits the persistence layer: session DB, long-term memory, Markdown memory, the work journal and checkpoints — none of it owned by the LLM.

## Autonomous Coding

The main agent (class `SHSCode` in `app/agent/shscode.py`) is a tool-calling agent with the PAORR loop:

```text
PLAN    → Decompose the task into clear, ordered sub-goals (first)
ACT     → Call a tool to execute one sub-goal
OBSERVE → Read tool output; extract key findings
REFLECT → Did this output solve the sub-goal? (yes/no, why)
RETRY   → If not solved: diagnose the failure, try a different tool/args
```

Behavioral guardrails baked into the loop:

- **Planning phase** — a numbered plan with success criteria is written before any tool call for non-trivial tasks.
- **Self-check every 3 steps** — the agent lists completed sub-goals, the current sub-goal, and the next concrete tool call.
- **Code review phase every 3 file edits** — correctness, edge cases, consistency, side effects, test coverage.
- **Loop detection** — identical tool + args signatures in a window are detected and the strategy is forced to change.
- **Duplicate nudge / goal-completion gate** — partial progress cannot be summarized as a final answer while DAG steps are pending (applies once real work started; pure Q&A still gets direct answers).
- **Termination discipline** — `terminate` may only be called when all sub-goals are complete AND verified; the reason must summarize accomplishments, verification results, and output paths.

Role-based teams are available through the multi-agent system (architect, product manager, engineer, QA), and an agent router maps channels/users/topics to different agent configurations.

## Persistent Memory

SHS Code maintains four independent memory/state systems. Each is persisted to disk, each survives restarts, model switches, provider switches, and context compaction, and each is verified by its own test suite (`tests/test_memory_layers.py`).

### Short-Term Memory

SQLite-backed session memory (`workspace/.sessions/shscode.db`): every message, tool call (with args, output, error, attempt, duration), step count, session state, errors and timestamps for the active session. Full-text search over messages is provided by FTS5. This is the conversation context the agent rehydrates when a session resumes.

### Long-Term Memory

SQLite-backed durable memory (`workspace/.memory/long_term.db`) with FTS keyword search and optional vector similarity when a vector library is available (graceful fallback otherwise). It stores durable facts: user preferences, coding preferences, project facts, architecture decisions, recurring instructions, useful task history. The agent stores and recalls via the memory system; recall results are injected into working context.

### Markdown Memory

Human-readable, human-editable Markdown files in the workspace:

- `MEMORY.md` — durable facts and knowledge the agent should always recall
- `USER.md` — user profile and preferences

The `memory` tool reads and writes them (`read_memory`, `write_memory`, `append_memory`, `read_user`, `write_user`). Being plain Markdown, they can be inspected and edited directly, put under version control, and shared across projects. They are separate from the SQLite layers: Markdown memory is for instructions and durable knowledge; SQLite long-term memory is for searchable episodic facts.

### Agent Work Notebook

The task journal (`workspace/.task_queue/journal.db`) is the agent's operational "what I did" record — deliberately lightweight and structured, not a transcript:

- what was inspected and changed (every tool call, success and failure)
- files modified (path, operation, timestamp — deduplicated, capped)
- commands and tests executed (with status)
- decisions made (with rationale)
- errors encountered and fixes applied (recovery actions)
- current position (step count, current step, phase, progress: completed / in-progress / pending)

The purpose: after context compaction, a model switch, an interruption, or a long-running task, the agent reads its own notes and knows exactly what it already did — instead of redoing work. Context summaries of recent steps are injected back into the conversation every few steps, and `/resume` restores the full picture from the journal.

## Persistent Work State

Beyond memory, SHS Code's work state is persistent and first-class:

- **Task journal** — every task row holds goal, status, progress, plan (DAG steps), file changes, commands, decisions, test results, recovery actions, and verification results.
- **Task queue** — background task execution with worker pool (multi-worker SQLite with correct thread ownership).
- **Checkpoints** — atomic JSON snapshots after every meaningful operation (see below).
- **Interruption handling** — at startup, tasks left in `running` by a crash/kill are marked `interrupted` (never silently restarted, never lost).
- **State resolution authority** — on resume, the real filesystem/Git state is authoritative; the journal is a record, not a source of truth. If the disk says otherwise, the agent re-inspects.

## Checkpoints & Recovery

```
START → WORK → CHECKPOINT → INTERRUPT → RESTART → RECOVER → INSPECT REAL STATE → CONTINUE → COMPLETE
```

- A checkpoint (goal, step count, conversation messages, provider/model, cwd) is written atomically after every tool call and step.
- Ctrl+C during a run interrupts cleanly — the task is checkpointed and marked interrupted; at the prompt, Ctrl+C exits cleanly.
- On next launch, SHS Code detects interrupted tasks and offers `/resume`: the checkpoint restores conversation state, the journal restores progress, and the filesystem/Git state is inspected before continuing.
- Crash recovery, stale-session recovery, and pause/resume are covered by dedicated regression tests (`tests/test_journal_recovery.py`, `tests/test_stabilization_fixes.py`).
- `/rollback [task]` restores agent-changed files from snapshot stores; SmartRollback integrates with Git state.

## Model & Provider System

The LLM layer is a multi-provider router (`app/llm/`):

| Built-in providers | Notes |
|---|---|
| `openai`, `anthropic`, `google`, `mistral`, `bedrock` | native SDK clients |
| `universal` | any OpenAI-compatible endpoint (Groq, OpenRouter, Together, NIM, vLLM, LM Studio, …) |
| `ollama` | local models |
| `gguf` | offline GGUF router |
| `huggingface` | HF inference |

On top of that:

- **Provider registry** — unlimited user-defined providers, persisted at `~/.shscode/providers.json`, each with its own API type, base URL, key, default model, headers, timeout, retries, and custom RPM.
- **Credential pools** — multiple API keys per provider with rotation; backends that reject per-call keys are handled correctly.
- **Provider health** — latency/token/cost tracking with 🟢🟡🔴 states, cooldown, and recommendations, wired into the retry loop.
- **Fallback & failover** — configurable triggers (rate limit, service unavailable, context window, quota) route to fallback models automatically; profile rotation rotates configured profiles.
- **Live switching** — `/model` and `/provider` rebuild the backend in place. Message history lives in agent memory, never in the LLM client, so switching can never destroy conversation state (regression-tested).
- **Token tracking** — per-request and cumulative budgets; `/usage` shows live stats.
- **Streaming, secret redaction, adaptive timeouts** — explicit user timeouts are honored exactly; adaptive defaults only apply when none is configured.

## Rate-Limit Handling

A true rolling-window limiter paces requests per provider/endpoint/model — never a naive "sleep 60s after each request".

Resolution order for the RPM limit:

1. **per-provider custom RPM** (provider registry entry)
2. **global custom RPM** (`[llm.rate_limit].rpm` when non-zero)
3. **provider default** — NVIDIA NIM endpoints: 40 RPM
4. **no limiter at all** — providers without a known default are not throttled

Key behaviors:

- **No artificial delay below the limit.** The limiter only engages when the rolling window is actually full; normal request flow is untouched.
- **Burst-friendly.** Requests fire back-to-back until capacity is reached; only then does the next request wait until the oldest timestamp leaves the 60-second window.
- **Server-side 429 handling.** `Retry-After` headers block until the stated moment — honored even for providers with no configured limit.
- **State preservation.** A rate-limit wait is a pure sleep: task context, conversation history and tool results live outside the LLM client and survive every wait (`rate_limit_wait` / `rate_limit_resume` events are emitted so the UI shows what is happening).
- **Recovery.** When the window slides or the block expires, work continues automatically from preserved state.

Configuration (`config.toml`):

```toml
[llm.rate_limit]
enabled = true
rpm     = 0   # 0 = automatic: provider default (NIM 40), others unlimited
```

Per-provider custom limit:

```
/provider add my-nim openai-compat https://integrate.api.nvidia.com/v1 meta/llama-3.1-70b-instruct nvapi-... 30
```

## Tools

17 tools are wired into the main agent (22 tool modules ship in total):

| Tool | Purpose |
|---|---|
| `python_execute` / `node_execute` | isolated subprocess execution |
| `bash` | persistent shell with full system access |
| `str_replace_editor` | view / create / edit any file |
| `browser_use` | Playwright browser automation (navigate, click, screenshot) |
| `web_search` | multi-engine search (DuckDuckGo/Bing/Google) with fallback |
| `crawl` | clean-text extraction from any URL |
| `image_generate` | text-to-image |
| `memory` | read/write Markdown memory files |
| `skill_manager` | create/patch/delete/list skills |
| `cross_session_search` | full-text search across all past sessions |
| `delegate` | spawn isolated subagents for parallel subtasks |
| `ask_human` | request clarification (blocks task, records why) |
| `code_search` | semantic / symbol / regex / import / usages search over the indexed project |
| `project_intel` | project summary, architecture map, entry points, env, Git state |
| `task_dag` | read/update the persisted plan; dependency-enforced completion |
| `verify` | project-aware build/test verification |
| `terminate` | signal verified task completion |

Every tool has a JSON-schema definition, argument validation, structured results, error surfaces, and its execution is journaled. Read-only tools are batched in parallel when safe.

## Skills

29 builtin skills ship in `app/skills/builtin/` covering languages and workflows: Python, JavaScript, TypeScript, Java, Kotlin, C, C++, C#, PHP, SQL, web/API/database/security engineering, DevOps, MLOps, debugging, testing, documentation, Git, GitHub, Linux, UI/UX, browser automation, automation, data analysis, research, android development.

Skills are loaded at four levels: `builtin`, `user` (`~/.shscode/skills/`), `project` (`.shscode/skills/`), and `installed` (`~/.shscode/skills/installed/`). A skill is a Markdown instruction file with optional metadata; the skill engine selects relevant skills for a task and injects their instructions into the agent context. Users can create, install, enable, disable and remove skills (`/skill`), with state persisted.

## MCP

Model Context Protocol support on both sides:

- **Client** — connect to MCP servers (stdio / SSE), discover their tools, and use them as native agent tools; resources and prompts are discovered where the server supports them. Multiple servers are supported; configuration lives in `config.toml`; auto-discovery from the SHS Code home directory.
- **Server** — SHS Code can expose its own tools via MCP with optional API-key authentication.

The full path is real: agent → MCP server → tool discovery → tool invocation → result into task state → agent continues. Connection failures, malformed responses, and unavailable servers are handled gracefully with recovery.

## Git & GitHub

- **Git intelligence** (`/git`) — status, diff, log, branches, remotes, staged/uncommitted awareness; repository-state detection feeds resume decisions (the filesystem/Git state is authoritative over journaled claims).
- **Forge connectors** — GitHub, GitLab, Azure DevOps, Bitbucket, and Forgejo providers (`/connectors`): tokens are stored per provider and feed the git-provider tools for repository inspection, issue/PR retrieval and creation where supported.
- **Workflow integration** — a realistic flow is first-class: inspect repository → understand issue → inspect relevant files (via `code_search`/`project_intel`) → implement change → run tests (`verify`) → commit → push/PR where supported. GitHub operations are connected to the agent execution system, not isolated utilities. Failures never destroy task state.

## Browser / Web

- `browser_use` — Playwright-driven navigation, interaction, screenshots
- `web_search` — multi-engine search with fallback
- `crawl` — clean text extraction from URLs
- `image_generate` — image generation

Web research results enter the agent's working state like any tool result and are journaled. Timeouts, redirects, unavailable pages and network failures are handled with retries and clear error surfaces.

## Multi-Agent System

- **Orchestrator** (`app/multi_agent.py`, `/multi-agent`) — DAG-based team execution with the role agents: Architect, Product Manager, Engineer, QA.
- **`delegate` tool** — the main agent spawns isolated subagents (own toolset, own session) for parallelizable subtasks; results return to the parent task state.
- **Agent router** — route by channel/user/topic to different agent configurations; falls back to the default SHSCode agent.
- Task delegation, result aggregation, failure propagation (one agent's failure never becomes another's success), and shared persistent state are covered by tests.

## Server & API

`shscode-server` (or `python run_server.py`) starts a FastAPI server:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | liveness |
| `POST /run` | async agent run (streams via activity events) |
| `POST /run/sync` | synchronous one-shot run |
| `GET /sessions` | session registry — accurate state (running/finished/failed/cancelled/interrupted/blocked), steps, messages, timestamps |
| `GET /sessions/{id}/messages` / `tool_calls` | full message and tool-call history |
| `GET /tools` | tool catalog |
| `WS /ws/{id}` | live event stream per session |
| `POST /multi-agent` | orchestrate a team run |
| `GET /chat`, `GET /canvas` | built-in web UIs |
| `WS /ws/chat/{id}`, `WS /ws/canvas/{id}` | web UI streams |

Webhooks (registered via API or `shscode-webhook`) trigger agent runs on external events, with signature verification. Optional API-key authentication (`SHSCODE_API_KEY`) and CORS restriction (`SHSCODE_ALLOWED_ORIGINS`). The session registry is synchronized with the real agent runtime and the session database — a session is never reported as running once its task has completed (regression-tested).

## CLI

`SHSCode` / `shscode` starts the interactive shell (one-shot: `shscode "task"`).

47 slash commands, all backed by real functionality:

```
Session/task   /tasks /task /resume /pause /stop /continue /bg /sessions
               /branch /new /checkpoint /history /context /compress /undo /retry
Model/provider /model /models /providers /provider /usage /profile /mode
Project        /project /env /search /files /git /verify /plan /rollback
Capabilities   /tools /skills /skill /mcp /channels /connectors /browser
Diagnostics    /status /doctor /log /debug /config /version /help /clear /exit
```

The shell features a live activity feed (thinking / tool calls / rate-limit waits / checkpoints), skins, plain-`exit`, and Ctrl+C-safe interruption. Additional console commands: `shscode-server`, `shscode-cron`, `shscode-multi`, `shscode-sessions`, `shscode-channels`, `shscode-webhook`.

## Channels & Connectors

13 messaging channels connect to the same underlying task/memory/state system (a task started from any channel uses the same intelligence and persistence — no isolated per-channel state):

Telegram, Slack, Discord, Matrix, IRC, WhatsApp, Email, Google Chat, Microsoft Teams, Signal, Twitch, WebChat, plus the built-in web chat.

The messaging gateway maps inbound messages to sessions, handles commands, streams progress, and survives reconnects, duplicate and malformed messages. Slack integration includes slash commands (`/shscode`, `/resolve`, `/review`) with Block Kit UI.

**Connectors** (`/connectors`) store per-forge credentials (GitHub, GitLab, Azure DevOps, Bitbucket, Forgejo) that feed the Git provider tools.

## Sandboxing

Three sandbox backends (`[sandbox]` in `config.toml`):

- `local` — the openshell executor (default)
- `docker` — containerized command execution
- `ssh` — remote execution over SSH

Each handles initialization, execution, timeouts, cleanup, failure reporting and task recovery. An SSH server mode is also available for remote gateway control with a restricted shell and public-key auth.

## Configuration

Layered, with sensible defaults:

1. Environment variables (`SHSCODE_*`, `.env`)
2. Profile dir: `~/.shscode/profiles/<name>/.env` + `config.yaml`
3. Project `config.toml`

```toml
[llm]
provider = "openai"        # or anthropic/google/mistral/bedrock/universal/ollama/gguf/huggingface
model    = "gpt-4o"
# base_url = "https://api.groq.com/openai/v1"   # universal provider
# api_key  = "sk-..."                            # or env: OPENAI_API_KEY / LLM_API_KEY

[llm.rate_limit]
enabled = true
rpm     = 0                # 0 = provider default (NIM 40), others unlimited

[mcp]                      # MCP servers
[[mcp.servers]]
name    = "filesystem"
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

[git_providers]            # forge tokens
github_token = "ghp_..."
```

Key environment variables: `SHSCODE_HOME` (default `~/.shscode`), `SHSCODE_WORKSPACE`, `SHSCODE_PROFILE`, `SHSCODE_API_KEY` (server auth), `SHSCODE_CIPHER_KEY` (secrets encryption), `SHSCODE_SSH_*`. Full reference in `docs/CONFIG.md`.

**Upgrade note:** installations from before the SHS Code rename are detected automatically — legacy `MANUSCLAW_*` environment variables, the `~/.manusclaw` home directory, and legacy session databases keep working without any action.

## Installation

**Requirements:** Python 3.11+ (optional: Node.js for `node_execute` and MCP servers; Docker for the docker sandbox; Playwright for browser automation).

```bash
# one-shot installer (venv + deps + SHSCode command)
curl -fsSL https://raw.githubusercontent.com/shslab-org/SHS-Code/main/install.sh | bash

# or from source
git clone https://github.com/shslab-org/SHS-Code.git && cd SHS-Code
pip install -e .
SHSCode
```

Docker:

```bash
docker build -t shscode:latest .
docker compose up          # interactive
docker compose run --rm shscode "Your task here"
```

Platform extras: `pip install -e ".[voice]"` (wake word + TTS), `".[ssh]"`, `".[gmail]"`, `".[matrix]"`, `".[companion]"`, `".[s3]"`, `".[gcs]"`, or `".[all-plus]"`. Windows: `install.ps1`. Termux: `setup-termux.sh`.

## Usage

```bash
# interactive shell
SHSCode

# one-shot task
shscode "write a Python script that dedupes CSV rows and explain it"

# pick a model/provider live
> /model meta/llama-3.1-70b-instruct
> /provider universal
> /status

# background + resume
> /bg run the full test suite and fix failures
> /tasks
> /resume

# health
> /doctor
```

## Examples

```text
> Fix the failing tests in tests/test_auth.py
  [plans] 1. run pytest to see failures  2. read the test + implementation
          3. locate the bug  4. fix  5. re-run until green  6. verify
  ...

> Explore this codebase and explain how authentication works
  [uses project_intel + code_search → structured answer, no files changed]

> Add a /health endpoint to the FastAPI app in app/server, with a test
  [edits files → runs pytest via verify → journals file changes → reviews
   its own diff after 3 edits → terminates with verification results]

> What did you do in the last task?
> [reads work notebook] Inspected app/auth.py, changed 2 files, ran
  pytest (613 passed), decided rolling-window over fixed sleep...
```

Long-running and multi-file tasks checkpoint after every step; interrupt any time (`Ctrl+C`) and `/resume` later — no work is redone (the agent re-reads its journal and re-verifies the real state).

## Architecture

```text
app/
├── agent/          SHSCode agent, base/ReAct/tool-call agents, roles, router,
│                   identity guard
├── cli.py          interactive shell + 47 slash commands
├── llm/            provider router, rate limiter, credential pool, retry,
│                   fallback, health, streaming, token tracking
├── memory/         long-term SQLite memory
├── db/             session DB (short-term memory)
├── state.py        task journal + checkpoints + state store
├── task_queue.py   background worker pool
├── intelligence/   AST indexer, semantic/structural search, profiles
├── planner.py      LLM + heuristic planners, task DAG
├── tools (tool/)   22 tool modules
├── skills/         skill engine + 29 builtin skills
├── mcp/            MCP client + server
├── git_intel.py    Git intelligence
├── git_providers/  GitHub/GitLab/Azure/Bitbucket/Forgejo
├── connectors.py   credential connector store
├── messaging/      13 channels + gateway
├── server/         FastAPI server, webhooks, web chat + canvas
├── sandbox/        local / docker / ssh executors
├── security/       secrets, cipher, security ensemble, identity guard
├── observability/  structured logging, tracing, health, correlation
├── compaction.py   structured context compaction
├── multi_agent.py  orchestrator + role teams
├── automation/     gmail watch, email tool
├── cron.py         scheduled tasks
├── desktop/        desktop companions (macOS/Windows/mobile)
└── flow/, nodes/, events/, hooks/, conversation/, context/ …
```

Detailed docs live in `docs/` (ARCHITECTURE, CONFIG, FEATURES, LOGGER, PROVIDERS).

## Testing

```bash
python -m pytest tests/ -q        # 653 passed, 2 skipped
```

The suite covers: the agent loop, rate limiting (rolling window, 429 recovery, precedence), model/provider switching with state preservation, interruption and crash recovery, journal/checkpoint behavior, all four memory layers, session registry accuracy, webhooks, channels, SSH, sandbox, skills, tools, intelligence indexing, planner/DAG, verification, and end-to-end multi-step workloads.

## Development

```bash
git clone https://github.com/shslab-org/SHS-Code.git
cd SHS-Code
pip install -e ".[all-plus]"
python -m pytest tests/ -q
python main.py            # dev entry
```

Core development principles (enforced across the codebase):

1. Never rebuild from scratch when a working implementation can be evolved.
2. Fix root causes; never hide errors to make tests pass.
3. The LLM is a replaceable reasoning engine — persistent SHS Code state must survive model, provider, rate-limit, network and process failures.
4. The real filesystem/Git state is authoritative on resume.
5. Every bug fix ships with a regression test.
6. Never mark incomplete work complete.

## Contributing

Issues and pull requests are welcome at [github.com/shslab-org/SHS-Code](https://github.com/shslab-org/SHS-Code). Keep changes aligned with the principles above; add regression tests for any behavior change; run the full suite before submitting. See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.

## License

Modified MIT License — see `LICENSE`. Copyright (c) 2025-2026 SHS Lab (Sazzad Hussain Shobuj).
