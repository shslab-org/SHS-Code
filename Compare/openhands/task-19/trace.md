# task-19 — T4 terminal + filesystem operations

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 7/10

## Canonical task prompt

**Turn 1:**

```
Do these steps in order: (1) find every TODO comment in the repository and write them to TODOS.txt as file:line entries. (2) create a directory named archive and copy every .md file from the repo root into it. (3) create a file .env.example containing exactly: FOO=bar. (4) show the final directory tree in your reply.
```

## Execution summary

- Turn 1: wall **330.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **10** total, 10 chat calls
- Upstream results: 8 OK, 1 HTTP 429, 0 HTTP 502
- Git: 4 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 6.86s | — | — |
| req2 | POST /chat/completions | — | 200 | 59.02s | — | 27.0 |
| req3 | POST /chat/completions | — | 200 | 17.59s | — | 1.9 |
| req4 | POST /chat/completions | — | 200 | 29.07s | — | 18.2 |
| req5 | POST /chat/completions | — | 200 | 36.04s | — | 23.1 |
| req6 | POST /chat/completions | — | 429 | 21.19s | — | 20.9 |
| req7 | POST /chat/completions | — | 200 | 42.16s | — | 33.3 |
| req8 | POST /chat/completions | — | 200 | 38.63s | — | 25.1 |
| req9 | POST /chat/completions | — | 200 | 40.39s | — | 20.4 |
| req10 | POST /chat/completions | — | — | —s | — | 13.9 |

## Final verification

```json
{
 "todos_has_readme_line": true,
 "archive_created": true,
 "md_copied": 2,
 "md_list": [
  "CHANGELOG.md",
  "README.md"
 ],
 "env_example": true
}
```

**Score justification:** checks 3/3 md_copied=2 [TIMEOUT] | t1=330.1s exit=-9 reqs=10 429=1 tools~8

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification