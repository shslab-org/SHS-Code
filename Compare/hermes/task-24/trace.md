# task-24 — R4 kill + resume reliability (kill at 75s)

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Implement a Caesar cipher: create cipher.py with encrypt(text, shift) and decrypt(text, shift) that shift letters (a-z, A-Z) by the given amount, preserving case and leaving non-letters untouched. Create test_cipher.py with at least 4 tests including a round-trip test. Run the full suite and make it pass.
```

**Turn 2:**

```
Continue your interrupted cipher task from where you left off and finish it completely.
```

## Execution summary

- Turn 1: wall **70.0s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **33** total, 9 chat calls
- Upstream results: 2 OK, 2 HTTP 429, 0 HTTP 502
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
| req14 | POST /chat/completions | — | — | —s | — | 34.0 |
| req15 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 34.27s | — | 34.0 |
| req16 | POST /chat/completions | — | — | —s | — | 34.0 |
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
| req29 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req30 | POST /chat/completions | — | — | —s | — | 34.0 |
| req31 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 34.0 |
| req32 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 97.18s | — | 34.0 |
| req33 | POST /chat/completions | — | — | —s | — | 34.0 |

## Final verification

```json
{
 "cipher_exists": false,
 "tests_exist": false,
 "suite": "10p/2f",
 "git_log_len": 3
}
```

**Score justification:** cipher checks 0/2 suite=10p/2f  | t1=70.0s exit=-9 reqs=33 429=2 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification