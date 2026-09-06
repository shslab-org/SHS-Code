# task-07 — P2 simple coding task (slugify)

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 2: Planning & Autonomous Execution
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Add a function slugify(text) to textproc.py: convert to lowercase, replace any run of non-alphanumeric characters with a single hyphen, collapse multiple hyphens, strip leading/trailing hyphens. slugify('') and slugify('   ') must return empty strings. Do not change other functions.
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
| req1 | POST /chat/completions | local-qwen3-1b | — | —s | — | — |

## Final verification

```json
{
 "error": "module 'textproc' has no attribute 'slugify'",
 "all_pass": false
}
```

**Score justification:** no slugify: module 'textproc' has no attribute 'slugify' [TIMEOUT] | t1=300.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification