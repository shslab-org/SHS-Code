# task-21 — R1 normal execution + timing

- **Agent**: SHS Code v2.2.0 (single agent)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 7/10

## Canonical task prompt

**Turn 1:**

```
Read README.md and write its first heading (the line starting with #) to HEADLINE.txt exactly as it appears. Then reply with the heading.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 7 OK, 1 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 51.05s | — | — |
| req2 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req3 | POST /chat/completions | — | 200 | 49.64s | — | 32.9 |
| req4 | POST /chat/completions | — | 200 | 31.87s | — | 17.2 |
| req5 | POST /chat/completions | — | 200 | 33.4s | — | 19.4 |
| req6 | POST /chat/completions | — | 200 | 42.19s | — | 20.0 |
| req7 | POST /chat/completions | — | 200 | 44.33s | — | 11.8 |
| req8 | POST /chat/completions | — | 200 | 24.41s | — | 1.4 |
| req9 | POST /chat/completions | — | — | —s | — | 11.0 |

## Final verification

```json
{
 "headline": "# benchlib \u2014 small utility library used for agent benchmarking",
 "correct": true
}
```

**Score justification:** headline correct in 300.1s (9 reqs) [TIMEOUT] | t1=300.1s exit=-9 reqs=9 429=1 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification