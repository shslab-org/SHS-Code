# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: SHS Code v3.1.0 (single agent)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 9/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **197.1s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **26** total, 26 chat calls
- Upstream results: 6 OK, 18 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 13 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | injected_502 | — |
| req2 | POST /chat/completions | — | — | —s | injected_502 | — |
| req3 | POST /chat/completions | — | 200 | 8.72s | — | — |
| req4 | POST /chat/completions | — | 200 | 1.22s | — | — |
| req5 | POST /chat/completions | — | 200 | 27.2s | — | — |
| req6 | POST /chat/completions | — | 429 | 0.24s | — | — |
| req7 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req8 | POST /chat/completions | — | 429 | 0.27s | — | — |
| req9 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req10 | POST /chat/completions | — | 429 | 0.27s | — | — |
| req11 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req12 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req13 | POST /chat/completions | — | 429 | 0.15s | — | — |
| req14 | POST /chat/completions | — | 429 | 0.13s | — | — |
| req15 | POST /chat/completions | — | 429 | 0.21s | — | — |
| req16 | POST /chat/completions | — | 429 | 0.24s | — | — |
| req17 | POST /chat/completions | — | 429 | 0.19s | — | — |
| req18 | POST /chat/completions | — | 429 | 0.15s | — | — |
| req19 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req20 | POST /chat/completions | — | 429 | 0.16s | — | — |
| req21 | POST /chat/completions | — | 429 | 0.2s | — | — |
| req22 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req23 | POST /chat/completions | — | 429 | 0.13s | — | — |
| req24 | POST /chat/completions | — | 200 | 25.51s | — | — |
| req25 | POST /chat/completions | — | 200 | 42.92s | — | — |
| req26 | POST /chat/completions | — | 200 | 16.41s | — | — |

## Final verification

```json
{
 "branch": "master",
 "correct": true
}
```

**Score justification:** survived 2 injected 502s, completed task | t1=197.1s exit=0 reqs=26 429=18 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification