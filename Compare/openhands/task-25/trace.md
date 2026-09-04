# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 7/10

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
- Turn 2: wall **129.5s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **13** total, 13 chat calls
- Upstream results: 4 OK, 8 HTTP 429, 0 HTTP 502
- Git: 1 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: see trace.jsonl

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.63s | — | 33.4 |
| req3 | POST /chat/completions | — | 429 | 33.12s | — | 32.9 |
| req4 | POST /chat/completions | — | 429 | 25.96s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 33.55s | — | 33.3 |
| req6 | POST /chat/completions | — | 429 | 33.04s | — | 32.8 |
| req7 | POST /chat/completions | — | 429 | 17.98s | — | 17.7 |
| req8 | POST /chat/completions | — | 429 | 33.64s | — | 33.4 |
| req9 | POST /chat/completions | — | — | —s | — | 32.9 |
| req10 | POST /chat/completions | — | 200 | 16.75s | — | 5.4 |
| req11 | POST /chat/completions | — | 200 | 29.99s | — | 22.6 |
| req12 | POST /chat/completions | — | 200 | 41.03s | — | 26.5 |
| req13 | POST /chat/completions | — | 200 | 23.66s | — | 19.5 |

## Final verification

```json
{
 "answer": "div",
 "correct": true
}
```

**Score justification:** context survived the model switch (div recalled) [TIMEOUT] | t1=300.1s exit=-9 reqs=13 429=8 tools~3; t2=129.5s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification