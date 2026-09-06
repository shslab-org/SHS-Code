# task-01 — M1 short-term context retention (2 turns, same session)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 8/10

## Canonical task prompt

**Turn 1:**

```
Read the files calc.py and textproc.py. Count the TOTAL number of function definitions (lines starting with 'def') across both files combined. Remember this number. Do not write it down anywhere yet. Reply with just the number.
```

**Turn 2:**

```
Without re-reading the files, write the total number of function definitions you counted in the previous step to a file named ANSWER.txt as plain digits only. Then reply with the number.
```

## Execution summary

- Turn 1: wall **254.1s**, exit `0`, finished
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **13** total, 13 chat calls
- Upstream results: 3 OK, 9 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.61s | — | 33.3 |
| req3 | POST /chat/completions | — | 429 | 33.17s | — | 32.9 |
| req4 | POST /chat/completions | — | 429 | 26.0s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 33.58s | — | 33.3 |
| req6 | POST /chat/completions | — | 429 | 33.09s | — | 32.8 |
| req7 | POST /chat/completions | — | 200 | 23.97s | — | 17.7 |
| req8 | POST /chat/completions | — | 200 | 28.93s | — | 27.7 |
| req9 | POST /chat/completions | — | 200 | 31.04s | — | 14.1 |
| req10 | POST /chat/completions | — | 429 | 17.23s | — | 17.0 |
| req11 | POST /chat/completions | — | 429 | 33.5s | — | 33.3 |
| req12 | POST /chat/completions | — | 429 | 33.2s | — | 32.9 |
| req13 | POST /chat/completions | — | — | —s | — | 25.7 |

## Final verification

```json
{
 "answer": "7",
 "correct": true,
 "note": "7 defs = 4 calc + 3 textproc; must be recalled without re-reading"
}
```

**Score justification:** recalled 7 without re-reading | t1=254.1s exit=0 reqs=13 429=9 tools~2; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification