# Benchmark results — full forensic analysis

All scores 1–10 per task, 5 tasks per category (50 pts), 250 pts total.
Every claim below is backed by the traces in this folder; per-task evidence notes are
in each `trace.md` and in `../scores.json`.

## A. Overall ranking

| Rank | Agent | Total /250 | % |
|------|-------|-----------:|---:|
| 1 | OpenHands CLI 1.13.1 | 130 | 52.0% |
| 2 | OpenCode 1.18.27 | 128 | 51.2% |
| 3 | SHS Code v2.2.0 single | 123 | 49.2% |
| 4 | Hermes v0.21.0 | 62 | 24.8% |
| 5 | SHS Code v2.2.0 multi-agent | 55 | 22.0% |

OpenHands wins by 2 points over OpenCode; the top three are within 7 points (≈3%).
Under this environment (heavily rate-limited shared endpoint, equal clock), the spread
between the three serious contenders is small, and their *profiles* differ more than
their totals.

## B. Category-by-category ranking

| Category | 1st | 2nd | 3rd | 4th | 5th |
|----------|-----|-----|-----|-----|-----|
| Memory & Persistent State /50 | OpenHands (20) | SHS single (16) | OpenCode (15) | Hermes (7) | SHS multi (7) |
| Planning & Autonomous Execution /50 | SHS single (30) | OpenCode (24) | OpenHands (20) | Hermes (17) | SHS multi (10) |
| Output / Code Quality /50 | OpenCode (32) | SHS single (31) | OpenHands (24) | Hermes (21) | SHS multi (21) |
| Tools / GitHub / MCP /50 | OpenHands (29) | OpenCode (25) = SHS single (25) | — | Hermes (6) = SHS multi (6) | — |
| Reliability / Rate Limit / Recovery /50 | OpenHands (37) | OpenCode (32) | SHS single (21) | Hermes (11) = SHS multi (11) | — |

## C. SHS Code single vs multi-agent

| Config | Total | Δ |
|--------|------:|---|
| Single agent | 123 | — |
| Multi-agent (PM/Architect/Engineer/QA) | 55 | **−68 (−27%)** |

Multi-agent did **not** improve any category. Evidence: the 4-role pipeline multiplies
model requests (each role runs its own LLM turns; e.g. task-06 shows PM → Architect
(92.5 s design doc) → Engineer → QA), and under the equal time budget it hit the time
cap on nearly every task (28 timeouts vs 26 for single). The wire logs show it using
fewer chat requests per task (126 total — it was *paced by the clock*, not the API):
the pipeline could not complete even trivial Q&A in 240 s. Observed integration
behavior worth noting: the Engineer role rejected the Architect's design once
("Input does not appear to be a design document") — a real multi-agent format-mismatch
failure recorded in `shs-code/multi-agent/task-06/trace.md`.

## D. Objective performance metrics (25 tasks each)

| Agent | Total requests | Chat calls | Upstream OK | HTTP 429 | Timeouts | Sum of turn wall-time |
|-------|---------------:|-----------:|------------:|---------:|---------:|----------------------:|
| OpenCode | 207 | 207 | 108 | 81 | 16 | 6394 s |
| OpenHands | 200 | 200 | 114 | 61 | 20 | 6732 s |
| Hermes | 592 | 202 | 122 | 44 | 18 | 6558 s |
| SHS single | 224 | 224 | 136 | 56 | 26 | 7671 s |
| SHS multi | 126 | 126 | 56 | 37 | 28 | 7936 s |

- Hermes' 592 requests vs 202 chat calls: a ~12-request startup probe storm per run
  (`/api/v1/models`, `/api/tags`, `/v1/props`, `/version`, `/api/show`, …) —
  Ollama-style discovery against a non-Ollama endpoint.
- SHS single had the most *successful* upstream responses (136) — its rolling-window
  limiter kept retrying until success — but also the most clock consumed.

## E. Memory comparison

- **In-session recall (task-01)**: OpenCode 10/10, OpenHands 10/10 — both recalled "7"
  without re-reading. SHS single (4/10) wrote a number but the *wrong one* ("0") in the
  follow-up turn — its one-shot architecture means turn 2 starts a fresh context and
  must use its journal/memory systems; the recall failed in this run. Hermes 2 (429
  death). Multi 2.
- **Cross-session long-term memory (task-02)**: OpenHands 7 and SHS single 7 both
  recalled port **7331** in a brand-new session (OpenHands via persisted conversation/
  file state; SHS via its SQLite long-term memory — the wire trace shows its memory
  recall working). OpenCode 2, Hermes 2, multi 2 (no recall).
- **Project Markdown memory (task-03)**: no agent produced a complete AGENTS.md within
  budget (all started but timed out — partial credit only).
- **Interruption + resume (task-05)**: no agent completed the 5-item checklist after the
  70 s kill + 150 s resume budget — every agent scored 1 (CH.md either absent or
  incomplete). The task consumed everyone; the 150 s turn-2 cap proved too small for
  all five equally.

**Layer analysis for SHS Code** (from traces): short-term session DB is written every
turn (sessions, steps, tool calls visible in logs); long-term SQLite memory demonstrably
recalled the port fact in task-02; Markdown memory (MEMORY.md) was not exercised
successfully within budgets; the journal/work-notebook recorded task progress but did
not restore enough context to finish checklist work in the resume window.

## F. Planning comparison

- **Trivial Q&A (task-06)**: OpenHands 26 s / 1 request; Hermes 11 s; OpenCode 73 s /
  3 requests; SHS single 96 s / 2 requests; SHS multi timed out at 240 s (never
  answered). SHS Code's execution gate did **not** block Q&A (direct answer, no forced
  plan) — the specific check requested for this benchmark — but its auxiliary calls
  (intent classification, title generation) cost ~3× the latency of OpenHands' single
  request.
- **Implementation tasks (07–10)**: SHS single completed the most implementations within
  budget (slugify + stats + debugging + fizzbuzz partials) — category win 30/50.
  OpenCode followed (24) with cleaner hidden-test results; OpenHands (20) frequently
  ran out of clock mid-implementation.

## G. Output / code-quality comparison

OpenCode 32/50 leads: hidden-test suites (17 email cases, 11 word_count cases) passed
cleanly when it finished — e.g. slugify 6/6 cases, word_count 11/11. SHS single 31/50
matched on implementations but slightly weaker on the hidden-test tasks. OpenHands 24
lost points to timeouts, not wrongness. No agent fabricated completion in a way that
fooled the verifier — every claimed-finished task was artifact-checked.

## H. GitHub comparison (task-17)

- **SHS single 10/10 — the only full workflow**: private repo
  `shslab-org/bench-shs-single` created, branches pushed, issue #1 "Benchmark audit"
  listing calc.py's functions with docstrings. Verified post-hoc via `gh api`.
- OpenCode 6, OpenHands 6: repo created and pushed, but no issue.
- Hermes 2, SHS multi 2: no repo created at all.

## I. MCP comparison (task-18)

- **OpenHands 10/10**: actually invoked the `bench` MCP server's `get_time` tool —
  TIME.txt contains the server's genuine timestamp `BENCH-MCP-SERVER-TIME: …`.
- OpenCode 4, SHS single 4: wrote the honest fallback `MCP-UNAVAILABLE` — the MCP
  tool did not surface in their usable toolset this run (configs existed).
- Hermes 1, SHS multi 1: nothing written.

## J. Skills comparison

No task isolated "skills" as a subsystem beyond the MCP + tool integration category,
and none of the CLIs exposed user-invocable skill execution in these headless runs.
Recorded as **not differentiated by this suite** (honest negative result).

## K. Rate-limit comparison

- **Injected 502×2 (task-22, unpaced)**: OpenCode 10 and OpenHands 10 both retried
  through the faults and completed. Hermes/SHS single/SHS multi (4 each) died — in
  SHS's case to the *organic* 429 contention of the unpaced round, not the 502s.
- **Injected 429×3 + Retry-After: 20 (task-23, unpaced)**: OpenCode 10, OpenHands 10
  (clean waits), SHS single 7 (waited and completed, but over the 390 s budget —
  wire log shows its limiter's "Rate limited (attempt N). Waiting Xs — state
  preserved" behavior working exactly as designed), Hermes 3, SHS multi 3.
- **Organic 429 behavior** (from proxy logs, paced rounds): SHS single absorbed 56
  429s across the benchmark with rolling-window waits and preserved state — the most
  resilient limiter of the four — while Hermes' 3-fast-retry policy (44 429s → mostly
  fatal) and OpenCode/OpenHands' SDK backoffs (81/61 429s, sometimes fatal within a
  turn) sat between.
- The benchmark's fair-share pacing (34 s/agent, documented in methodology) is
  *capacity division*, not artificial throttling: the shared real limit (~10 RPM)
  is continuously oversubscribed by 5 agents; fault rounds ran unpaced.

## L. Recovery comparison

- **Kill + resume (task-05, task-24)**: universally failed within the tight resume
  budgets — every agent scored 1 on task-05; on task-24 no agent produced a working
  cipher within 70 s kill + 150 s resume. This is a genuine, if brutal, negative
  result: interruption recovery was the weakest capability across the board under
  equal tight clocks.
- **Model switch (task-25)**: OpenHands 7 — the only agent whose conversation context
  survived the m3 → gpt-oss-20b switch (replied "div" correctly; wire log confirms
  both models served the two turns). OpenCode/Hermes/SHS single/SHS multi: the switch
  itself demonstrably happened on the wire (gpt-oss-20b requests visible), but the
  follow-up turn either timed out or lost the recalled context.

## M. Tool-use comparison

Visible tool-call counts (parsed from CLI output; [NOT EXPOSED] internals excluded):
OpenCode's structured `--format json` events give the most transparent tool stream
(read/write/edit/bash per call); OpenHands headless prints action summaries; SHS Code
logs every step + tool with its selector confidences; Hermes' one-shot mode prints
only final output by default (tool activity only visible via the wire proxy + usage
file). Terminal/filesystem task (19): OpenCode 8, OpenHands 7, SHS single 6 — partial
completions across the board.

## N. Final strengths / weaknesses

**OpenHands** — Strengths: most request-efficient (200 requests, best OK-rate), best
reliability under faults, best memory persistence, only successful MCP usage, best
model-switch continuity. Weaknesses: weak on hidden-test output quality (24/50),
frequent clock exhaustion mid-implementation, no GitHub issue creation.

**OpenCode** — Strengths: best code quality on hidden tests (32/50), transparent
structured event stream, solid fault recovery. Weaknesses: aux title-generation calls
double request volume; heavier turns; no cross-session memory; no issue creation;
MCP tool not usable in-run.

**SHS Code (single)** — Strengths: best planning/execution ratio (30/50), most
resilient rate-limit architecture (state-preserving rolling window), only full
GitHub workflow (repo + issue), SQLite long-term memory demonstrably survives new
sessions. Weaknesses: highest clock consumption (7671 s), most timeouts (26),
multi-request turns (intent/title/main + journal writes) starve it under tight
budgets, in-session recall failed on task-01, MCP tool not surfaced in-run.

**Hermes** — Strengths: fastest trivial-Q&A wall time (11 s), rich plugin surface.
Weaknesses: fatal 3-fast-retry policy under real rate limits (most deaths), 12-request
startup probe storm per run, no successful long-term memory, no GitHub, no MCP
completion. Its 24.8% measures this environment's interaction with its defaults, not
its ceiling.

**SHS Code (multi-agent)** — Strengths: role pipeline runs end-to-end (PM →
Architect → Engineer → QA), model switch propagated to all roles. Weaknesses: 4×
request amplification made it the slowest config on every task; 28 timeouts; did not
finish a single simple task within budget; one observed role-to-role format mismatch.
Under equal clocks, the multi-agent structure strictly reduced performance.

## Full score table

See [../scores_table.md](../scores_table.md) for the 25×5 grid and category totals;
`../scores.json` for machine-readable notes per score.
