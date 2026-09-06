# task-07 — P2 simple coding task (slugify)

- **Agent**: SHS Code v3.1.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 2: Planning & Autonomous Execution
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Add a function slugify(text) to textproc.py: convert to lowercase, replace any run of non-alphanumeric characters with a single hyphen, collapse multiple hyphens, strip leading/trailing hyphens. slugify('') and slugify('   ') must return empty strings. Do not change other functions.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **2** total, 2 chat calls
- Upstream results: 1 OK, 0 HTTP 429, 0 HTTP 502
- Git: 12 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 204.3s | — | — |
| req2 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "error": "module 'textproc' has no attribute 'slugify'",
 "all_pass": false
}
```

**Score justification:** no slugify: module 'textproc' has no attribute 'slugify' [TIMEOUT] | t1=300.1s exit=-9 reqs=2 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification