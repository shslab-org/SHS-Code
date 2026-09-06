# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: OpenCode 1.18.27
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8391 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **72.0s**, exit `1`, finished
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 0 OK, 7 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | injected_502 | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | injected_502 | — |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.2s | — | — |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.12s | — | — |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.07s | — | — |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.12s | — | — |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.12s | — | — |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.23s | — | — |
| req9 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.27s | — | — |

## Final verification

```json
{
 "branch": "",
 "correct": false
}
```

**Score justification:** died after faults (ok=0, 429=7) | t1=72.0s exit=1 reqs=9 429=7 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification