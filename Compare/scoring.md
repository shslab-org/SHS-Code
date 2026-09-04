# Scoring methodology

## Scale (identical for every agent)

10 exceptional / complete / correct / efficient / well verified · 9 excellent ·
8 very strong · 7 good · 6 acceptable · 5 mixed · 4 weak · 3 poor · 2 severely
deficient · 1 failed or almost entirely unsuccessful.

Every score is computed from **objective evidence** — answer-file contents, hidden
tests, git state, wire-level logs, and trace events — never from the agent's final
self-report. The full machine-readable scores live in `../scores.json`; the generator
is `../score.py` (deterministic formulas below).

## Rubric per task

Each task has a deterministic check function (`../tasks.py` → `verify(workdir)`) that
inspects the post-run repository. Scores derive from those checks, with adjustments
for timeouts and bonus dimensions. Formulas (identical for all agents):

| Task | Determininistic basis | Notes |
|------|----------------------|-------|
| 01 in-session recall | `ANSWER.txt == "7"` → 8–10 (speed-graded); else 2–4 | correct number of `def`s across both files |
| 02 cross-session memory | `PORT.txt == "7331"` in a NEW session → 9–10; else 2–3 | long-term memory task |
| 03 project memory file | 6 boolean checks (exists, calc, textproc, pytest, failing-tests, >400 chars) → 1 + 9×fraction | |
| 04 work notebook | worklog exists (2) + function implemented (2) + tests pass (2) + stages marked (≤3) | is_palindrome task |
| 05 interrupt + resume | all 5 checklist items checked + DONE.txt → 10; else 1 + 2·CH.md exists + checked count | killed at 70 s, then resumed |
| 06 trivial Q&A | answer "4" → 8–10 (graded by speed and request count); else 2 | measures unnecessary planning/tool spam |
| 07 slugify | 6 hidden cases (incl. `''`, `'   '`, punctuation) → 1 + 9×fraction | |
| 08 stats module | 7 checks (module, mean, median odd/even, empty-error, tests, suite green) | |
| 09 debugging | suite green + implementation fixed + tests untouched (3 each); +1 if root cause stated | |
| 10 fizzbuzz + self-verify | 5 hidden cases + tests exist + suite green → 10 | edge case n=0 |
| 11 email validator | 17 hidden tests → 1 + 9×fraction | spec-exact validator |
| 12 word_count fix | 11 hidden tests + regression tests added | |
| 13 Calculator refactor | class + methods + original tests still pass; wrapper check for 10 | |
| 14 test quality | 6 checks (coverage of both fns, empty/unicode/multi-space edges, impl untouched) + new-test count | |
| 15 README | 9 checks (no TODO, install, usage, real signatures, test instructions, …) | |
| 16 git branch workflow | 5 checks (branch, conventional commit, logger.py, tests pass, main untouched) | |
| 17 GitHub | repo exists (6) + issue with calc.py functions (10); verified via `gh api` post-hoc | |
| 18 MCP | real `BENCH-MCP-SERVER-TIME` in TIME.txt → 10; honest MCP-UNAVAILABLE fallback → 4 | |
| 19 terminal/filesystem | TODOs file:line + archive + .env.example + md copies | |
| 20 release workflow | version 0.2.0 + changelog + RELEASE.md + branch + commit (5 checks) | |
| 21 normal execution | headline correct → 9–10 (speed-graded) | timing metrics |
| 22 injected 502×2 | completed despite faults → 9–10; recovered but incomplete → 4; dead → 1 | unpaced round |
| 23 injected 429×3 + Retry-After | completed after waiting → 9–10 | unpaced round |
| 24 kill + resume | cipher checks (exists, roundtrip, shift, case, tests) + suite; −1 for duplicate commits | killed at 75 s |
| 25 model switch | `SAFEFUNC.txt == "div"` → 10 (context survived the switch) | wire log confirms the switch |

## Global rules (uniform)

- **Timeout cap**: any turn killed by the time cap (except the designed kill tasks 05
  and 24) caps the score at 7 and is tagged `[TIMEOUT]` in the evidence note.
- **Duplicate-work penalty** (task 24): commits beyond the 3-commit baseline deduct 1.
- **No brand priors**: formulas never reference the agent's identity.

## Category totals

Each category = 5 tasks × 10 = 50 points. Overall = 250. Percentage = total/250×100.

## Category and overall results

| Agent | Memory /50 | Planning /50 | Output /50 | Tools /50 | Reliability /50 | Total /250 | % |
|-------|-----------:|-------------:|-----------:|----------:|----------------:|------------:|---:|
| OpenHands | 20 | 20 | 24 | 29 | **37** | **130** | 52.0% |
| OpenCode | 15 | 24 | **32** | 25 | 32 | 128 | 51.2% |
| SHS Code (single) | 16 | **30** | 31 | 25 | 21 | 123 | 49.2% |
| Hermes | 7 | 17 | 21 | 6 | 11 | 62 | 24.8% |
| SHS Code (multi) | 7 | 10 | 21 | 6 | 11 | 55 | 22.0% |

Per-task table: `../scores_table.md`. Every per-task score's evidence note is included
in each `trace.md` ("Score justification") and in `../scores.json`.
