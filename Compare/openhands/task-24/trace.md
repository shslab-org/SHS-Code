# task-24 — R4 kill + resume reliability (kill at 75s)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
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
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **7** total, 7 chat calls
- Upstream results: 0 OK, 5 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req2 | POST /chat/completions | — | — | —s | — | 33.4 |
| req3 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req4 | POST /chat/completions | — | 429 | 33.67s | — | 33.4 |
| req5 | POST /chat/completions | — | 429 | 33.11s | — | 32.8 |
| req6 | POST /chat/completions | — | 429 | 25.94s | — | 25.7 |
| req7 | POST /chat/completions | — | — | —s | — | 33.3 |

## Final verification

```json
{
 "cipher_exists": false,
 "tests_exist": false,
 "suite": "10p/2f",
 "git_log_len": 3
}
```

**Score justification:** cipher checks 0/2 suite=10p/2f  | t1=70.1s exit=-9 reqs=7 429=5 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification