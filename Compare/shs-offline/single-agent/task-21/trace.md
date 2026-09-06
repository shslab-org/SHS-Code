# task-21 — R1 normal execution + timing

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Read README.md and write its first heading (the line starting with #) to HEADLINE.txt exactly as it appears. Then reply with the heading.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **1** total, 1 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 18 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "headline": "",
 "correct": false
}
```

**Score justification:** HEADLINE.txt='' [TIMEOUT] | t1=300.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification