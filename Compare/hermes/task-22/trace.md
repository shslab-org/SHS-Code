# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 4/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **57.5s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **17** total, 5 chat calls
- Upstream results: 3 OK, 3 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | — | —s | injected_502 | — |
| req2 | GET /api/tags | — | — | —s | injected_502 | — |
| req3 | GET /v1/props | — | 404 | 0.17s | — | — |
| req4 | GET /props | — | 404 | 0.06s | — | — |
| req5 | GET /version | — | 404 | 0.06s | — | — |
| req6 | GET /models | — | 200 | 0.06s | — | — |
| req7 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req8 | GET /v1/models | — | 404 | 0.06s | — | — |
| req9 | POST /api/show | — | 404 | 0.06s | — | — |
| req10 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req11 | GET /v1/models | — | 404 | 0.06s | — | — |
| req12 | POST /api/show | — | 404 | 0.06s | — | — |
| req13 | POST /chat/completions | — | — | —s | — | — |
| req14 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 16.9s | — | — |
| req15 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req16 | POST /chat/completions | — | 429 | 0.16s | — | — |
| req17 | POST /chat/completions | — | 200 | 24.77s | — | — |

## Final verification

```json
{
 "branch": "",
 "correct": false
}
```

**Score justification:** died after faults (ok=3, 429=3) | t1=57.5s exit=0 reqs=17 429=3 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification