# task-24 — R4 kill + resume reliability (kill at 75s)

- **Agent**: SHS Code v3.1.0 (single agent)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
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
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **8** total, 8 chat calls
- Upstream results: 0 OK, 7 HTTP 429, 0 HTTP 502
- Git: 19 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.32s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 33.47s | — | 33.3 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 33.19s | — | 33.0 |
| req4 | POST /chat/completions | — | 429 | 29.1s | — | 28.8 |
| req5 | POST /chat/completions | — | 429 | 33.54s | — | 33.3 |
| req6 | POST /chat/completions | — | 429 | 33.05s | — | 32.8 |
| req7 | POST /chat/completions | — | 429 | 32.01s | — | 31.7 |
| req8 | POST /chat/completions | — | — | —s | — | 33.3 |

## Final verification

```json
{
 "cipher_exists": false,
 "tests_exist": false,
 "suite": "10p/2f",
 "git_log_len": 3
}
```

**Score justification:** cipher checks 0/2 suite=10p/2f  | t1=70.0s exit=-9 reqs=8 429=7 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification