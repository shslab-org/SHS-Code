# Results — v3 final window (2026-09-06) + frozen v2 baseline

Scoring: deterministic artifact verification per task, 1–10, 25 tasks × 5
categories (memory / planning / output / tools / reliability), 250 max.
Every number below traces to files in this directory.

## A. Overall ranking (final)

| Rank | Agent | Total /250 | % | vs v2 |
|------|-------|-----------:|---:|------:|
| 1 | **SHS Code v3.1.0 single** | **149** | **59.6%** | 80 → 149 (**+69**) |
| 2 | OpenCode 1.18.28 (frozen v2) | 74 | 29.6% | — |
| 2 | OpenHands CLI 1.13.1 (frozen v2) | 74 | 29.6% | — |
| 4 | SHS Code v3.1.0 multi | 78 | 31.2% | 59 → 78 (**+19**) |
| 5 | Hermes 0.19.0 (frozen v2) | 57 | 22.8% | — |
| — | SHS v3.1.0 offline single (local 1B) | 50 | 20.0% | new |
| — | SHS v3.1.0 offline multi (local 1B) | 50 | 20.0% | new |

No agent broke 52% in either the v1 or v2 windows. SHS Code v3.1.0 is the
first configuration to do so (59.6%) — and it did it under the same degraded
4–6 RPM weather that capped everyone else at 29.6%.

## B. Category-by-category (final)

| Agent | Memory /50 | Planning /50 | Output /50 | Tools /50 | Reliability /50 |
|-------|-----------:|-------------:|-----------:|----------:|----------------:|
| SHS v3.1.0 single | **28** | **32** | **29** | **32** | 28 |
| OpenCode | 7 | 28 | 23 | 10 | 6 |
| OpenHands | 13 | 10 | 21 | 10 | **20** |
| SHS v3.1.0 multi | 7 | 18 | 21 | 6 | 26 |
| Hermes | 7 | 10 | 23 | 6 | 11 |

SHS single leads 4 of 5 categories. OpenHands keeps the reliability crown
from v2 (20) — but SHS single closed the gap from 18→28 while OpenHands
stayed frozen.

## C. SHS Code: what 3 evidence-driven upgrade rounds changed

v2.2.0 (v1 pilot, 123/250) → v3.0.1 (v2 window, 80/250 under 51%-429 weather)
→ **v3.1.0 (this run, 149/250)**. Per-task deltas of the final round:

```
task:  01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25
v3.0.1  7  2  1  3  1  8  2  1  4  1  1  3  4  7  6  1  7  1  1  1  7  7  1  1  2
v3.1.0  8  7  7  3  3 10  7  1  7  7  1  7  7  7  7  5  7 10  7  3  9  9  7  1  2
        +1 +5 +6  0 +2 +2 +5  0 +3 +6  0 +4 +3  0 +1 +4  0 +9 +6 +2 +2 +2 +6  0  0
```

Largest single-agent gains and their causes (all fixable weaknesses were
found in this benchmark's own traces):

- **task-18 (MCP): 1 → 10.** v2's SHS honestly reported `MCP-UNAVAILABLE`
  (the old harness only configured the bench MCP server for competitors).
  With the fairness fix + v3.1.0 MCP-in-main-agent, SHS *actually called*
  the MCP tool and wrote the real server timestamp. Evidence:
  `shs-code/single-agent/task-18/result.json`.
- **task-03 (memory file): 1 → 7.** The v3.1 memory round (tool-fact
  distillation into long-term memory + MEMORY.md/USER.md injection) now
  writes the requested long-term memory file with all 6 content checks.
- **task-02 (cross-session recall): 2 → 7.** "port recalled in a NEW session"
  — the four-layer memory architecture (SQLite LTM/FTS) finally carries a
  fact stored in session 1 into a fresh session 2. This was the single
  biggest structural gap vs OpenHands in v1.
- **task-07 (slugify hidden tests): 2 → 7.** All hidden cases pass now
  (request-budget fix: short prompts skip the LLM planner call).
- **task-10 (fizzbuzz): 1 → 7.** 5/5 hidden cases + test file + suite.
- **task-23 (injected 429s): 1 → 7.** Handled 3 injected 429s with
  Retry-After and *completed* — adaptive rolling-window limiter.
- **task-06 (Q&A): 8 → 10.** "2+2" answered in **3.5 s with 1 request**
  (v2: 71.5 s, 3 requests) — the chat fast-path/classify_request work.

## D. Single vs multi-agent (still open)

Multi improved +19 (59 → 78) but remains 71 points behind single (149).
Task-06/21/22/23 now score equal (multi's triage + session continuity fixes
landed), and multi *survives* fault injection (task-22: 4 → 9). But
multi-agent still loses wherever request budget is the binding constraint:
orchestration amplifies request count under the shared 4–6 RPM cap.
Evidence: `shs-code/multi-agent/task-01/proxy.jsonl` (2 requests before
timeout vs single's 11).

## E. Offline round (new): pipeline robust, model is noise

Setup: `Qwen3.8-1.0B-A0.6B` served locally (OpenAI-compatible, CPU, 2 cores)
through the same forensic proxies; identical tasks/budgets/fault injection;
pace disabled (no rate limit locally).

- **64 total requests, 0 completed responses.** Thinking-mode generations
  (2048-token cap) at ~6.6 tok/s ≈ 310 s exceed all task budgets. Every
  task timed out with requests in flight — score floor 50/250 (20%).
- **The model itself is untrained.** Its card says `create-tiny-model`
  ("for testing and development"); live verification: greedy logits are
  flat noise (std 0.64), "The capital of France is" yields multilingual
  gibberish. It cannot answer "2+2" under any sampler. Offline scores
  measure SHS Code's plumbing with a noise model — not 1B capability.
- **What did get verified offline:** correct OpenAI wire contract end-to-end
  (chat + tools + tool_calls parsing + usage), model-name switching accepted
  (task-25 model switch executed), harness/proxy/agent lifecycle with zero
  crashes and zero 500s, RAM headroom (model 2.2 GB + agent on a 3 GB box).

## F. Request efficiency (the v1 finding, still true)

| Agent | Total requests (25 tasks) | OK | 429 absorbed | Timeouts |
|-------|--------------------------:|---:|-------------:|---------:|
| SHS single (v3) | ~250 | ~210 | ~30 (0 organic) | 14 |
| OpenCode (v2 frozen) | ~230 | ~120 | ~110 | 66 |
| OpenHands (v2 frozen) | ~270 | ~140 | ~130 | 66 |

Under a shared ~4–6 RPM cap with fair-share pacing, the winner is the agent
that converts *each* request into verified work. SHS v3.1.0 does this best:
its 4 biggest category jumps (tools +21, memory +21, planning +16) all came
from spending requests on the actual task instead of re-planning, re-nudging
and re-asking.

## G. Reliability under injected faults (category 5, identical for all)

| Agent | task-22 (2× injected 502) | task-23 (3× injected 429 + Retry-After) |
|-------|--------------------------|------------------------------------------|
| SHS v3.1.0 single | survived, completed (9) | handled all 3, completed (7) |
| SHS v3.1.0 multi | survived, completed (9) | handled all 3, completed (7) |
| OpenCode (v2) | died (1) | failed (1) |
| OpenHands (v2) | died (1) | failed (1) |
| Hermes (v2) | died (4) | failed (3) |

## H. Remaining weaknesses (honest list)

- SHS single: task-08 (stats module) and task-11 (hidden email tests) still
  fail to implement; task-24 cipher and task-25 model-switch context still
  score at floor; many wins are still [TIMEOUT]-capped at 7 — more requests
  per budget would convert several 7s into 9s/10s.
- SHS multi: request amplification under shared caps; needs budget-aware
  orchestration (single-agent fallback exists but triggers too late).
- Offline: needs a *trained* small model to be meaningful.

## Full score table

See [../scores_table.md](../scores_table.md) for the 25×7 matrix and
`scores.json` for machine-readable scores + per-task evidence notes.
