# SHS Code Forensic Benchmark — OpenCode vs OpenHands vs Hermes vs SHS Code

A controlled, fair, fully-traced performance comparison of four CLI coding agents,
executed 2026-09-04 on identical tasks with the same model through the same endpoint.

## Result (TL;DR)

| Rank | Agent | Memory /50 | Planning /50 | Output /50 | Tools /50 | Reliability /50 | **Total /250** | **%** |
|------|-------|-----------:|-------------:|-----------:|----------:|----------------:|---------------:|------:|
| 1 | **OpenHands** (CLI 1.13.1) | 20 | 20 | 24 | 29 | **37** | **130** | **52.0%** |
| 2 | **OpenCode** (1.18.27) | 15 | 24 | **32** | 25 | 32 | **128** | **51.2%** |
| 3 | **SHS Code** v2.2.0 single agent | 16 | **30** | 31 | 25 | 21 | **123** | **49.2%** |
| 4 | **Hermes** (v0.21.0) | 7 | 17 | 21 | 6 | 11 | **62** | **24.8%** |
| 5 | **SHS Code** v2.2.0 multi-agent (PM/Architect/Engineer/QA) | 7 | 10 | 21 | 6 | 11 | **55** | **22.0%** |

No agent exceeded 52%. Under a heavily rate-limited shared model endpoint with equal
time budgets, *request efficiency* mattered as much as capability: every task in every
category is scored from the actual artifact, never from the final message.

Full details: [results.md](results.md) · methodology: [methodology.md](methodology.md) ·
rubric: [scoring.md](scoring.md) · full score table: [../scores_table.md](../scores_table.md)

## Benchmark setup

| Item | Value |
|------|-------|
| Model | `minimaxai/minimax-m3` (identical for every agent) |
| Provider / endpoint | NVIDIA NIM — `https://integrate.api.nvidia.com/v1` (free tier) |
| Rate-limit reality | **Not 40 RPM.** Measured live: token-bucket ≈ 2–3 request burst, ~10 RPM sustained, ~10–15 s cooldown on `429` (no `Retry-After` header from NIM). Endpoint `deprecation: 2026-09-09`. |
| Agents | OpenCode 1.18.27 · OpenHands CLI 1.13.1 (headless) · Hermes Agent v0.21.0 (`-z` one-shot) · SHS Code v2.2.0 (`shscode` one-shot) · SHS Code multi-agent pipeline (`run_multi_agent.py`, PM→Architect→Engineer→QA) |
| Task suite | 5 categories × 5 tasks = 25 canonical tasks, identical prompts for every agent |
| Starting state | Fresh copy of the same 3-commit `benchlib` repository per run |
| Time budgets | Identical per task (240–390 s per turn), enforced identically (SIGKILL at cap) |
| Model switch task | turn 2 switches to `openai/gpt-oss-20b` for every agent |
| Forensic capture | Every agent routed through a local wire-level proxy: full request/response logs (secrets redacted), plus full CLI stdout/stderr, git diffs, and post-hoc artifact verification |

## Trace layout

```
Compare/
├── README.md               ← this file
├── methodology.md          ← fairness + harness design + limitations
├── scoring.md              ← 1–10 rubric and per-task formulas
├── results.md              ← rankings, category winners, analyses A–N
├── opencode/task-01…25/    ← trace.md · trace.jsonl · proxy.jsonl · diff.patch · result.json
├── openhands/task-01…25/
├── hermes/task-01…25/
└── shs-code/
    ├── single-agent/task-01…25/
    └── multi-agent/task-01…25/
```

Every task directory lets you reconstruct: exact prompt → model → init → model requests
(wire-level, with status codes, durations, 429/502 events, pacing waits) → visible tool
calls → terminal/file actions (in `diff.patch`) → final artifact checks → score with
evidence. What a CLI does not expose (e.g. its internal system prompt) is marked
**[NOT EXPOSED]** — nothing is fabricated.

## Category winners (evidence in results.md)

- **Memory & persistent state**: OpenHands (20/50) — best cross-session persistence
  (port-7331 recall in a new session; model-switch recall).
- **Planning & autonomous execution**: SHS Code single (30/50) — most completed
  implementations within budget (slugify, stats, debugging, fizzbuzz, Caesar partials).
- **Output / code quality**: OpenCode (32/50) — best hidden-test pass rates
  (slugify 6/6, email validator, word_count regression suite).
- **Tools / GitHub / MCP / integrations**: OpenHands (29/50) — the only agent that
  successfully used the MCP server tool; GitHub repo creation tie with OpenCode/SHS.
- **Reliability / rate-limit / recovery**: OpenHands (37/50) — survived injected 502s,
  injected 429+Retry-After, and organic 429 storms with the fewest requests per task.
- **Best overall**: OpenHands (130/250), by a 2-point margin over OpenCode.

## Key findings

1. **The stated 40 RPM does not exist for this model.** Controlled probing of
   `minimaxai/minimax-m3` showed a ~2–3-request burst bucket (~10 RPM sustained).
   Five concurrent agents oversubscribe it permanently; the benchmark therefore
   divides capacity fairly (see methodology) and additionally measures raw
   retry behavior in unpaced fault-injection rounds (tasks 22/23).
2. **Hermes' default retry policy is fatal under real rate limits.** ~3 fast retries
   (~0.5–2 s apart) inside a 10–15 s cooldown window: it died on the first organic 429
   in most rounds (evidence: `hermes/*/trace.md`, "API call failed after 3 retries").
   It also fired the most requests per turn (592 total, incl. a ~12-request startup
   probe storm: `/api/tags`, `/v1/props`, `/api/show`, …).
3. **SHS Code's rate-limit architecture is the most resilient** (rolling-window waits
   with state preservation — visible in traces: "Rate limited (attempt N) … Waiting Xs
   — state preserved"), but its per-turn request count is high, so under equal time
   budgets it often ran out of clock, not capability.
4. **SHS Code multi-agent (PM/Architect/Engineer/QA) was SLOWER, not better** under the
   same time budget: the 4-role pipeline multiplies requests (each role = its own LLM
   calls) and hit the time cap on most tasks. Multi-agent did not improve any category.
5. **Memory (task-02)**: OpenHands and SHS Code single both recalled the deployment port
   across a brand-new session; OpenCode/Hermes/multi did not.
6. **Model switch (task-25)**: OpenHands preserved conversation context across the
   m3 → gpt-oss-20b switch and answered correctly; every other agent either timed out
   mid-recovery or lost context (SHS Code's switch itself worked — the wire log shows
   gpt-oss-20b requests — but the fresh one-shot turn did not finish in budget).
7. **GitHub (task-17)**: only SHS Code single completed the full workflow
   (private repo + push + issue listing calc.py functions). OpenCode/OpenHands created
   the repo but no issue; Hermes and SHS multi created nothing.

## Limitations (honest)

- One execution per agent per task (no repetition variance; forensics over statistics).
- minimax-m3 latency (10–90 s/response, extended reasoning on large prompts) + shared
  capacity meant many tool-heavy tasks hit the time cap for everyone; partial credit
  is scored from artifacts, and the cap applied identically to all agents.
- System prompts are internal to each CLI and marked [NOT EXPOSED]; only observable
  behavior is compared.
- SHS Code is compared against release versions of its competitors as installed from
  their official channels on the run date.

## Raw evidence

- Per-task traces: 125 directories under this folder (625 files, all secret-scanned).
- Raw run data: `../runs/` (harness output), `../scores.json`, `../metrics.json`.
- Harness: `../harness.py`, tasks: `../tasks.py`, proxy: `../../scripts/bench_proxy.py`.

## Earlier pilot run (same day, 06:12 UTC)

An earlier 40-run pilot (4 CLIs × 5 tasks × 2 models: gpt-oss-20b + minimax-m3) from
this same investigation is preserved under [pilot-0612/](pilot-0612/) for continuity.
The pilot used a different task set and scoring model; the benchmark documented in
this README supersedes it.
