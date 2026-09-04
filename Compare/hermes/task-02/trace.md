# task-02 — M2 long-term memory across sessions (2 new sessions)

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Important project fact to remember for future sessions: this project's deployment port is 7331 and the preferred test runner is pytest. Store this in your persistent long-term memory. Reply DONE when stored.
```

**Turn 2:**

```
Without asking me any question: what is this project's deployment port? If you know it or can find it from what you previously stored, write ONLY the port number to a file named PORT.txt. If you truly cannot determine it, write UNKNOWN.
```

## Execution summary

- Turn 1: wall **110.0s**, exit `0`, finished
- Turn 2: wall **111.6s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **31** total, 7 chat calls
- Upstream results: 5 OK, 4 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.17s | — | — |
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
| req14 | POST /chat/completions | — | 429 | 34.26s | — | 34.0 |
| req15 | POST /chat/completions | — | 429 | 30.98s | — | 30.7 |
| req16 | POST /chat/completions | — | 429 | 28.61s | — | 28.4 |
| req17 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req18 | GET /api/tags | — | 404 | 0.06s | — | — |
| req19 | GET /v1/props | — | 404 | 0.06s | — | — |
| req20 | GET /props | — | 404 | 0.06s | — | — |
| req21 | GET /version | — | 404 | 0.06s | — | — |
| req22 | GET /models | — | 200 | 0.06s | — | — |
| req23 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req24 | GET /v1/models | — | 404 | 0.06s | — | — |
| req25 | POST /api/show | — | 404 | 0.06s | — | — |
| req26 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req27 | GET /v1/models | — | 404 | 0.06s | — | — |
| req28 | POST /api/show | — | 404 | 0.06s | — | — |
| req29 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 26.0 |
| req30 | POST /chat/completions | — | 200 | 62.51s | — | 34.0 |
| req31 | POST /chat/completions | — | 200 | 41.22s | — | 31.3 |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** PORT.txt='' | t1=110.0s exit=0 reqs=31 429=4 tools~0; t2=111.6s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification