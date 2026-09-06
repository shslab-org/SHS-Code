# task-23 — R3 rate-limit injection (429 + Retry-After)

- **Agent**: SHS Code v3.1.0 OFFLINE (multi-agent, local 1B model)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8397 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Write the names of the Python modules (files, not tests) in this repository to MODULES.txt, one per line, then reply with them.
```

## Execution summary

- Turn 1: wall **390.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **1** total, 1 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 15 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "modules": "",
 "correct": false
}
```

**Score justification:** failed after injected 429s (ok=0) [TIMEOUT] | t1=390.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification