# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **144.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **15** total, 15 chat calls
- Upstream results: 0 OK, 13 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | injected_502 | — |
| req2 | POST /chat/completions | — | — | —s | injected_502 | — |
| req3 | POST /chat/completions | — | 429 | 0.26s | — | — |
| req4 | POST /chat/completions | — | 429 | 0.14s | — | — |
| req5 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req6 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req7 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req8 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req9 | POST /chat/completions | — | 429 | 0.13s | — | — |
| req10 | POST /chat/completions | — | 429 | 0.24s | — | — |
| req11 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req12 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req13 | POST /chat/completions | — | 429 | 0.29s | — | — |
| req14 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req15 | POST /chat/completions | — | 429 | 0.12s | — | — |

## Final verification

```json
{
 "branch": "",
 "correct": false
}
```

**Score justification:** died after faults (ok=0, 429=13) | t1=144.0s exit=0 reqs=15 429=13 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification