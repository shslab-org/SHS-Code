# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: SHS Code v2.2.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
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

- Turn 1: wall **227.1s**, exit `1`, finished
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 1 OK, 6 HTTP 429, 0 HTTP 502
- Git: 5 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: see trace.jsonl

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.2s | — | — |
| req2 | POST /chat/completions | — | 429 | 32.98s | — | 32.8 |
| req3 | POST /chat/completions | — | 429 | 31.06s | — | 30.9 |
| req4 | POST /chat/completions | — | 429 | 27.55s | — | 27.4 |
| req5 | POST /chat/completions | — | 429 | 20.43s | — | 20.2 |
| req6 | POST /chat/completions | — | 429 | 6.07s | — | 5.9 |
| req7 | POST /chat/completions | — | — | —s | — | — |
| req8 | POST /chat/completions | — | 200 | 79.18s | — | 33.3 |
| req9 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) | t1=227.1s exit=1 reqs=9 429=6 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification