# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: SHS Code v2.2.0 (single agent)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Read calc.py. Which function performs safe division (raising on zero divisor)? Remember its exact name. Reply with just the function name.
```

**Turn 2:**

```
Write the name of the function you identified in the previous turn to Write the name of the function you identified in the previous turn to a file named SAFEFUNC.txt (create it). Reply with the function name.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **14** total, 14 chat calls
- Upstream results: 5 OK, 7 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: see trace.jsonl

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.18s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.0s | — | 32.8 |
| req3 | POST /chat/completions | — | 429 | 31.6s | — | 31.4 |
| req4 | POST /chat/completions | — | 429 | 29.0s | — | 28.8 |
| req5 | POST /chat/completions | — | 429 | 23.31s | — | 23.1 |
| req6 | POST /chat/completions | — | 429 | 11.86s | — | 11.7 |
| req7 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req8 | POST /chat/completions | — | 200 | 59.05s | — | 32.8 |
| req9 | POST /chat/completions | — | — | —s | — | 7.7 |
| req10 | POST /chat/completions | — | 200 | 73.84s | — | 17.1 |
| req11 | POST /chat/completions | — | 200 | 10.54s | — | — |
| req12 | POST /chat/completions | — | 200 | 36.98s | — | 23.5 |
| req13 | POST /chat/completions | — | 200 | 28.0s | — | 20.5 |
| req14 | POST /chat/completions | — | — | —s | — | 26.5 |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) [TIMEOUT] | t1=300.1s exit=-9 reqs=14 429=7 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification