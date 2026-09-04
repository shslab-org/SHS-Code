# task-22 — R2 provider fault resilience (2 injected 502s)

- **Agent**: SHS Code v2.2.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 4/10

## Canonical task prompt

**Turn 1:**

```
Write the name of the current git branch to BRANCH.txt, then reply with the branch name.
```

## Execution summary

- Turn 1: wall **126.5s**, exit `1`, finished
- Model requests (wire-level, via forensic proxy): **10** total, 10 chat calls
- Upstream results: 1 OK, 7 HTTP 429, 0 HTTP 502, 0 injected-429, 2 injected-502
- Git: 3 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | injected_502 | — |
| req2 | POST /chat/completions | — | — | —s | injected_502 | — |
| req3 | POST /chat/completions | — | 429 | 0.18s | — | — |
| req4 | POST /chat/completions | — | 200 | 31.47s | — | — |
| req5 | POST /chat/completions | — | 429 | 0.08s | — | — |
| req6 | POST /chat/completions | — | 429 | 0.07s | — | — |
| req7 | POST /chat/completions | — | 429 | 0.07s | — | — |
| req8 | POST /chat/completions | — | 429 | 0.07s | — | — |
| req9 | POST /chat/completions | — | 429 | 0.07s | — | — |
| req10 | POST /chat/completions | — | 429 | 0.2s | — | — |

## Final verification

```json
{
 "branch": "",
 "correct": false
}
```

**Score justification:** died after faults (ok=1, 429=7) | t1=126.5s exit=1 reqs=10 429=7 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification