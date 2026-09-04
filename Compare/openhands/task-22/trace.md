# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 10/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **75.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **5** total, 5 chat calls
- Upstream results: 3 OK, 0 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 1 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | injected_502 | — |
| req2 | POST /chat/completions | — | — | —s | injected_502 | — |
| req3 | POST /chat/completions | — | 200 | 21.39s | — | — |
| req4 | POST /chat/completions | — | 200 | 25.63s | — | — |
| req5 | POST /chat/completions | — | 200 | 9.38s | — | — |

## Final verification

```json
{
 "branch": "master",
 "correct": true
}
```

**Score justification:** survived 2 injected 502s, completed task | t1=75.0s exit=0 reqs=5 429=0 tools~2

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification