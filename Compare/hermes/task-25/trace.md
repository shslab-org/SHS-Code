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

- Turn 1: wall **74.5s**, exit `0`, finished
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **66** total, 8 chat calls
- Upstream results: 6 OK, 3 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: see trace.jsonl

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.18s | — | — |
| req2 | GET /api/tags | — | 404 | 0.06s | — | — |
| req3 | GET /v1/props | — | 404 | 0.06s | — | — |
| req4 | GET /props | — | 404 | 0.06s | — | — |
| req5 | GET /version | — | 404 | 0.06s | — | — |
| req6 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req7 | GET /api/tags | — | 404 | 0.06s | — | — |
| req8 | GET /v1/props | — | 404 | 0.06s | — | — |
| req9 | GET /props | — | 404 | 0.06s | — | — |
| req10 | GET /version | — | 404 | 0.06s | — | — |
| req11 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req12 | GET /api/tags | — | 404 | 0.06s | — | — |
| req13 | GET /v1/props | — | 404 | 0.06s | — | — |
| req14 | GET /props | — | 404 | 0.06s | — | — |
| req15 | GET /version | — | 404 | 0.06s | — | — |
| req16 | GET /models | — | 200 | 0.06s | — | — |
| req17 | POST /api/show | — | 404 | 0.06s | — | — |
| req18 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req19 | GET /api/tags | — | 404 | 0.06s | — | — |
| req20 | GET /v1/props | — | 404 | 0.06s | — | — |
| req21 | GET /props | — | 404 | 0.06s | — | — |
| req22 | GET /version | — | 404 | 0.06s | — | — |
| req23 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req24 | GET /v1/models | — | 404 | 0.06s | — | — |
| req25 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req26 | GET /api/tags | — | 404 | 0.06s | — | — |
| req27 | GET /v1/props | — | 404 | 0.06s | — | — |
| req28 | GET /props | — | 404 | 0.06s | — | — |
| req29 | GET /version | — | 404 | 0.06s | — | — |
| req30 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req31 | POST /chat/completions | — | 429 | 31.08s | — | 30.8 |
| req32 | POST /chat/completions | — | 429 | 29.58s | — | 29.3 |
| req33 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req34 | GET /api/tags | — | 404 | 0.06s | — | — |
| req35 | GET /v1/props | — | 404 | 0.06s | — | — |
| req36 | GET /props | — | 404 | 0.06s | — | — |
| req37 | GET /version | — | 404 | 0.06s | — | — |
| req38 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req39 | GET /api/tags | — | 404 | 0.06s | — | — |
| req40 | GET /v1/props | — | 404 | 0.06s | — | — |
| … | (26 more in proxy.jsonl) | | | | | |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) | t1=74.5s exit=0 reqs=66 429=3 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification