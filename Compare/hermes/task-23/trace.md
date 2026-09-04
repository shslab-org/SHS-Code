# task-23 — R3 rate-limit injection (429 + Retry-After)

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 3/10

## Canonical task prompt

**Turn 1:**

```
Write the names of the Python modules (files, not tests) in this repository to MODULES.txt, one per line, then reply with them.
```

## Execution summary

- Turn 1: wall **390.2s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **23** total, 5 chat calls
- Upstream results: 4 OK, 1 HTTP 429, 0 HTTP 502, 3 injected-429, 0 injected-502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.18s | — | — |
| req2 | GET /api/tags | — | 404 | 0.06s | — | — |
| req3 | GET /v1/props | — | — | —s | injected_429 | — |
| req4 | GET /props | — | — | —s | injected_429 | — |
| req5 | GET /version | — | — | —s | injected_429 | — |
| req6 | GET /models | — | 200 | 0.06s | — | — |
| req7 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req8 | GET /v1/models | — | 404 | 0.06s | — | — |
| req9 | POST /api/show | — | 404 | 0.06s | — | — |
| req10 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req11 | GET /v1/models | — | 404 | 0.06s | — | — |
| req12 | POST /api/show | — | 404 | 0.06s | — | — |
| req13 | POST /chat/completions | — | — | —s | — | — |
| req14 | POST /chat/completions | minimaxai/minimax-m3 | 504 | 302.14s | — | — |
| req15 | POST /chat/completions | — | 200 | 16.59s | — | — |
| req16 | GET /api/v1/models | — | 404 | 0.17s | — | — |
| req17 | GET /api/tags | — | 404 | 0.06s | — | — |
| req18 | GET /v1/props | — | 404 | 0.06s | — | — |
| req19 | GET /props | — | 404 | 0.06s | — | — |
| req20 | GET /version | — | 404 | 0.06s | — | — |
| req21 | GET /models | — | 200 | 0.06s | — | — |
| req22 | POST /chat/completions | — | 200 | 5.11s | — | — |
| req23 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "modules": "",
 "correct": false
}
```

**Score justification:** failed after injected 429s (ok=4) [TIMEOUT] | t1=390.2s exit=-9 reqs=23 429=1 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification