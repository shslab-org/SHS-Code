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

- Turn 1: wall **70.1s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **103.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **64** total, 6 chat calls
- Upstream results: 3 OK, 4 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

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
| req10 | GET /version | — | 404 | 0.07s | — | — |
| req11 | GET /api/v1/models | — | 404 | 0.07s | — | — |
| req12 | GET /api/tags | — | 404 | 0.06s | — | — |
| req13 | GET /v1/props | — | 404 | 0.06s | — | — |
| req14 | GET /props | — | 404 | 0.07s | — | — |
| req15 | GET /version | — | 404 | 0.06s | — | — |
| req16 | GET /models | — | 200 | 0.06s | — | — |
| req17 | POST /api/show | — | 404 | 0.06s | — | — |
| req18 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req19 | GET /api/tags | — | 404 | 0.07s | — | — |
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
| req30 | POST /chat/completions | — | 200 | 10.29s | — | — |
| req31 | POST /chat/completions | — | 429 | 23.84s | — | 23.6 |
| req32 | POST /chat/completions | — | — | —s | — | 31.3 |
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
 "cipher_exists": false,
 "tests_exist": false,
 "suite": "10p/2f",
 "git_log_len": 3
}
```

**Score justification:** cipher checks 0/2 suite=10p/2f  | t1=70.1s exit=-9 reqs=64 429=4 tools~0; t2=103.0s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification