# Benchmark methodology

## Objective

A controlled, fair, reproducible, forensic comparison of CLI coding agents:
OpenCode, OpenHands, Hermes, SHS Code (single + multi-agent), using the same model
(`minimaxai/minimax-m3`), the same provider (NVIDIA NIM free endpoint), the same
task prompts, the same starting repository state, and the same time budgets.

## Environment

| Item | Detail |
|------|--------|
| Machine | single Linux container, Python 3.12, Node 24, one shared NVIDIA NIM account |
| Model | `minimaxai/minimax-m3` for all agents and all tasks (model switch task uses `openai/gpt-oss-20b` on turn 2 for every agent) |
| Endpoint | `https://integrate.api.nvidia.com/v1` (NVIDIA NIM free tier) |
| API key | one key, shared by all agents (redacted from all traces) |
| Agents & versions | OpenCode 1.18.27 (npm `opencode-ai`), OpenHands CLI 1.13.1 (pip `openhands`, headless mode), Hermes Agent v0.21.0 (official installer), SHS Code v2.2.0 (repo at commit `fe9a80f`) |
| Agent defaults | every CLI ran with its own default configuration; the only modifications were provider/model wiring (identical values for all) and the benchmark MCP server (`bench`) configured identically in all four CLIs |

## Discovered rate-limit reality

The task specification assumed "40 RPM". Controlled measurement (sequential probing,
clean windows) showed the actual limit for `minimaxai/minimax-m3` on the free tier is a
token bucket: ~2–3 requests per burst, sustained ~10 requests/minute, ~10–15 s cooldown
after a 429, with **no Retry-After header** returned by NIM. The endpoint also advertises
`deprecation: 2026-09-09`.

This discovery drove two design decisions:

1. **Fair capacity division for capability rounds.** Five concurrent agents permanently
   oversubscribe a ~10 RPM shared bucket. Without intervention the benchmark measures
   only retry-storm survival (early pilots: every agent failing most tasks with 429
   cascades). Each agent's requests pass through its own forensic proxy; in normal
   (passthrough) rounds the proxy enforces a **minimum 34 s spacing between forwarded
   chat-completions per agent** (≈ 5 agents × <2 RPM aggregate ≈ well under capacity).
   This is *capacity division*, not throttling below a real limit — the shared real
   limit is continuously oversubscribed, and the same rule applies to every agent.
   Discovery probes (model lists, 404s) pass unpaced.
2. **Raw (unpaced) fault-injection rounds.** Category 5 tasks 22–23 run with pacing
   disabled, injecting deterministic faults (2× HTTP 502; then 3× HTTP 429 +
   `Retry-After: 20`). Here agents face the real contention plus injected faults and
   their native retry/backoff behavior is measured exactly as shipped.

All pacing events are recorded in each `proxy.jsonl` (`paced_wait` events with wait
durations) — nothing is hidden.

## Fairness controls

- **Same prompt**: 25 canonical prompts (see `../tasks.py`) sent verbatim to every
  agent. Turn-2 prompts (resume/switch) also identical.
- **Same starting state**: every run receives a fresh copy of the same 3-commit
  `benchlib` repo; per-agent isolated directories; git state reset per run.
- **Same model**: all agents wired to `minimaxai/minimax-m3` via the same base URL and
  key. Verified on the wire: the proxy log records the model name of every request.
- **Same time budget**: per-task timeouts identical across agents, enforced by SIGKILL
  on the whole process group. Kill-based tasks (05, 24) kill every agent at the same
  wall-clock offset (70 s / 75 s).
- **Same environment**: same machine, same network path, same gh CLI + token available
  to all agents for the GitHub task, same MCP server (`bench`) configured in all four
  CLIs.
- **No manual help**: agents were never hand-fed answers or corrected mid-run.
- **Start-order rotation**: within each round the five agents launch staggered 20 s
  apart in a rotating order (task index modulo 5) so no agent always occupies the
  "fresh bucket" slot.
- **Scoring blind to brand**: every score derives from post-hoc artifact checks,
  wire-level logs, and trace evidence (see scoring.md) — not from the agents'
  self-reported final messages.

## Forensic trace capture

Each agent × task run is captured at three levels:

1. **Wire level** — every HTTP request/response through the agent's dedicated proxy:
   method, path, model, status, duration, bytes, 429/502 events, injected faults,
   pacing waits. Secrets redacted (key → `[REDACTED]`; structure preserved).
2. **CLI level** — full stdout+stderr with per-line timestamps (`trace.jsonl`), parsed
   into visible tool-call events in `trace.md`.
3. **Artifact level** — `git add -A && git diff HEAD` → `diff.patch`; post-hoc
   deterministic verification (`result.json` checks); GitHub state via `gh api`
   for the repo/issue task.

What a CLI does not expose (internal system prompt, hidden chain-of-thought, private
planning text) is recorded as **[NOT EXPOSED]** — never fabricated.

## Task suite

5 categories × 5 tasks = 25 tasks (full definitions with verification functions in
`../tasks.py`):

- **Category 1 — Memory & persistent work state**: in-session recall (01), cross-session
  long-term memory (02), project Markdown memory (03), staged work notebook (04),
  interruption + resume (05, killed at 70 s then resumed).
- **Category 2 — Planning & autonomous execution**: trivial Q&A (06), simple feature
  (07), multi-file implementation (08), debugging (09), implement-and-verify loop (10).
- **Category 3 — Output / code quality / verification**: hidden-test email validator
  (11), hidden-test bug fix (12), backwards-compatible refactor (13), test quality
  (14), documentation rewrite (15).
- **Category 4 — Tools / GitHub / MCP / integrations**: git branch workflow (16),
  GitHub repo + issue creation (17), MCP tool usage (18), terminal/filesystem
  operations (19), combined release workflow (20).
- **Category 5 — Reliability / rate limit / recovery**: normal execution timing (21),
  injected provider 502s (22, unpaced), injected 429+Retry-After (23, unpaced),
  kill + resume (24, killed at 75 s), model switch mid-conversation (25).

## Known limitations

- One run per agent per task — variance is not estimated; the traces compensate with
  complete evidence per run.
- Time budgets (240–390 s) bind tightly under minimax-m3 latency (10–90 s per response
  with extended reasoning on large prompts); timeouts hit all agents, and partial
  credit is scored from artifacts. Slower-clock agents (SHS multi-agent especially)
  are penalized by the equal-clock design — which is the point of an equal-budget
  comparison, but it is a limitation of interpretation.
- The five agents have different internal architectures (aux "small" calls, title
  generation, probe storms) that consume shared capacity; per-agent request counts are
  published as objective metrics so the reader can weigh capability vs. efficiency.
- Hermes' fast-fail retry behavior means its scores largely reflect rate-limit
  fragility rather than coding capability; this is its observed, as-shipped behavior
  and is reported as such.
- The NIM endpoint deprecates 2026-09-09; reproduction after that date requires the
  model to still be served.
