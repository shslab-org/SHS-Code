# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
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

- Turn 1: wall **110.0s**, exit `0`, finished
- Turn 2: wall **141.6s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **33** total, 9 chat calls
- Upstream results: 4 OK, 4 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: ['minimaxai/minimax-m3', 'openai/gpt-oss-20b']

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.18s | — | — |
| req2 | GET /api/tags | — | 404 | 0.06s | — | — |
| req3 | GET /v1/props | — | 404 | 0.06s | — | — |
| req4 | GET /props | — | 404 | 0.06s | — | — |
| req5 | GET /version | — | 404 | 0.06s | — | — |
| req6 | GET /models | — | 200 | 0.06s | — | — |
| req7 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req8 | GET /v1/models | — | 404 | 0.06s | — | — |
| req9 | POST /api/show | — | 404 | 0.06s | — | — |
| req10 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req11 | GET /v1/models | — | 404 | 0.06s | — | — |
| req12 | POST /api/show | — | 404 | 0.06s | — | — |
| req13 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req14 | POST /chat/completions | — | 429 | 34.25s | — | 34.0 |
| req15 | POST /chat/completions | — | 429 | 31.2s | — | 30.9 |
| req16 | POST /chat/completions | — | 429 | 29.65s | — | 29.4 |
| req17 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req18 | GET /api/tags | — | 404 | 0.06s | — | — |
| req19 | GET /v1/props | — | 404 | 0.06s | — | — |
| req20 | GET /props | — | 404 | 0.06s | — | — |
| req21 | GET /version | — | 404 | 0.06s | — | — |
| req22 | GET /models | — | 200 | 0.06s | — | — |
| req23 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req24 | GET /v1/models | — | 404 | 0.06s | — | — |
| req25 | POST /api/show | — | 404 | 0.06s | — | — |
| req26 | GET /v1/models/openai/gpt-oss-20b | — | 404 | 0.06s | — | — |
| req27 | GET /v1/models | — | 404 | 0.06s | — | — |
| req28 | POST /api/show | — | 404 | 0.06s | — | — |
| req29 | POST /chat/completions | — | — | —s | — | 25.9 |
| req30 | POST /chat/completions | openai/gpt-oss-20b | — | —s | — | 34.0 |
| req31 | POST /chat/completions | openai/gpt-oss-20b | 200 | 32.32s | — | — |
| req32 | POST /chat/completions | — | — | —s | — | 34.0 |
| req33 | POST /chat/completions | openai/gpt-oss-20b | 200 | 100.9s | — | 34.0 |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) | t1=110.0s exit=0 reqs=33 429=4 tools~0; t2=141.6s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification