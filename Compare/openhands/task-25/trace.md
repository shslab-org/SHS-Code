# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 10/10

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

- Turn 1: wall **288.1s**, exit `0`, finished
- Turn 2: wall **135.6s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **13** total, 13 chat calls
- Upstream results: 6 OK, 7 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: see trace.jsonl

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.59s | — | 33.3 |
| req3 | POST /chat/completions | — | 429 | 33.1s | — | 32.9 |
| req4 | POST /chat/completions | — | 429 | 26.03s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 33.56s | — | 33.3 |
| req6 | POST /chat/completions | — | 200 | 35.77s | — | 32.9 |
| req7 | POST /chat/completions | — | 429 | 31.35s | — | 31.1 |
| req8 | POST /chat/completions | — | 429 | 33.51s | — | 33.3 |
| req9 | POST /chat/completions | — | 200 | 34.12s | — | 32.9 |
| req10 | POST /chat/completions | — | 200 | 26.0s | — | 17.8 |
| req11 | POST /chat/completions | — | 200 | 33.89s | — | 25.7 |
| req12 | POST /chat/completions | — | 200 | 30.71s | — | 25.8 |
| req13 | POST /chat/completions | — | 200 | 29.65s | — | 29.1 |

## Final verification

```json
{
 "answer": "div",
 "correct": true
}
```

**Score justification:** context survived the model switch (div recalled) | t1=288.1s exit=0 reqs=13 429=7 tools~4; t2=135.6s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification