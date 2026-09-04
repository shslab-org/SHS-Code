# task-21 — R1 normal execution + timing

- **Agent**: SHS Code v2.2.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Read README.md and write its first heading (the line starting with #) to HEADLINE.txt exactly as it appears. Then reply with the heading.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **3** total, 3 chat calls
- Upstream results: 2 OK, 0 HTTP 429, 0 HTTP 502
- Git: 5 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 142.02s | — | — |
| req2 | POST /chat/completions | — | 200 | 129.39s | — | — |
| req3 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "headline": "",
 "correct": false
}
```

**Score justification:** HEADLINE.txt='' [TIMEOUT] | t1=300.1s exit=-9 reqs=3 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification