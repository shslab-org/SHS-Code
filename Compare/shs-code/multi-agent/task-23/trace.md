# task-23 — R3 rate-limit injection (429 + Retry-After)

- **Agent**: SHS Code v2.2.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 3/10

## Canonical task prompt

**Turn 1:**

```
Write the names of the Python modules (files, not tests) in this repository to MODULES.txt, one per line, then reply with them.
```

## Execution summary

- Turn 1: wall **390.2s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **5** total, 5 chat calls
- Upstream results: 2 OK, 0 HTTP 429, 0 HTTP 502, 3 injected-429, 0 injected-502
- Git: 5 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 89.41s | — | — |
| req2 | POST /chat/completions | — | 200 | 214.57s | — | — |
| req3 | POST /chat/completions | — | — | —s | injected_429 | — |
| req4 | POST /chat/completions | — | — | —s | injected_429 | — |
| req5 | POST /chat/completions | — | — | —s | injected_429 | — |

## Final verification

```json
{
 "modules": "",
 "correct": false
}
```

**Score justification:** failed after injected 429s (ok=2) [TIMEOUT] | t1=390.2s exit=-9 reqs=5 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification