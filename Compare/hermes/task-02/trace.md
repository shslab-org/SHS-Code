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

- Turn 1: wall **83.5s**, exit `0`, finished
- Turn 2: wall **93.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **64** total, 6 chat calls
- Upstream results: 4 OK, 4 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.18s | — | — |
| req2 | GET /api/tags | — | 404 | 0.06s | — | — |
| req3 | GET /v1/props | — | 404 | 0.06s | — | — |
| req4 | GET /props | — | 404 | 0.06s | — | — |
| req5 | GET /version | — | 404 | 0.07s | — | — |
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
| req30 | POST /chat/completions | — | 200 | 8.35s | — | — |
| req31 | POST /chat/completions | — | 429 | 25.85s | — | 25.6 |
| req32 | POST /chat/completions | — | 200 | 40.44s | — | 30.9 |
| req33 | GET /api/v1/models | — | 404 | 0.17s | — | — |
| req34 | GET /api/tags | — | 404 | 0.06s | — | — |
| req35 | GET /v1/props | — | 404 | 0.06s | — | — |
| req36 | GET /props | — | 404 | 0.06s | — | — |
| req37 | GET /version | — | 404 | 0.06s | — | — |
| req38 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req39 | GET /api/tags | — | 404 | 0.06s | — | — |
| req40 | GET /v1/props | — | 404 | 0.06s | — | — |
| … | (24 more in proxy.jsonl) | | | | | |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** PORT.txt='' | t1=83.5s exit=0 reqs=64 429=4 tools~0; t2=93.0s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification