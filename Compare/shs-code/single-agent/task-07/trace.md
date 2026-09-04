# task-07 — P2 simple coding task (slugify)

- **Agent**: SHS Code v2.2.0 (single agent)
- **Category**: Category 2: Planning & Autonomous Execution
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 7/10

## Canonical task prompt

**Turn 1:**

```
Add a function slugify(text) to textproc.py: convert to lowercase, replace any run of non-alphanumeric characters with a single hyphen, collapse multiple hyphens, strip leading/trailing hyphens. slugify('') and slugify('   ') must return empty strings. Do not change other functions.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **8** total, 8 chat calls
- Upstream results: 6 OK, 1 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 17.09s | — | — |
| req2 | POST /chat/completions | — | 429 | 17.13s | — | 16.9 |
| req3 | POST /chat/completions | — | 200 | 49.27s | — | 32.8 |
| req4 | POST /chat/completions | — | 200 | 20.09s | — | 17.5 |
| req5 | POST /chat/completions | — | 200 | 51.34s | — | 31.4 |
| req6 | POST /chat/completions | — | 200 | 26.79s | — | 14.1 |
| req7 | POST /chat/completions | — | 200 | 90.33s | — | 21.3 |
| req8 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "cases": {
  "'Hello World'": true,
  "'A B'": true,
  "''": true,
  "'   '": true,
  "'Hello,  World!!'": true,
  "'abc  def'": true
 },
 "all_pass": true
}
```

**Score justification:** all slugify hidden cases pass [TIMEOUT] | t1=300.1s exit=-9 reqs=8 429=1 tools~1

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification