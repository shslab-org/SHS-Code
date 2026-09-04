# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: OpenCode 1.18.27
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8391 forensic proxy)
- **Score**: 10/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **84.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 3 OK, 4 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 2 changed paths, 3 commits
- Visible tool calls in trace: 1

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | injected_502 | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | injected_502 | — |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.22s | — | — |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 6.78s | — | — |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.07s | — | — |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.24s | — | — |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 6.77s | — | — |
| req9 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 0.8s | — | — |

## Tool calls (as visible in CLI output)

- `[82.5s]` tool:bash

## Final verification

```json
{
 "branch": "master",
 "correct": true
}
```

**Score justification:** survived 2 injected 502s, completed task | t1=84.0s exit=0 reqs=9 429=4 tools~1

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification