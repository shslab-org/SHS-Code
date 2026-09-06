# task-19 — T4 terminal + filesystem operations

- **Agent**: SHS Code v3.1.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Do these steps in order: (1) find every TODO comment in the repository and write them to TODOS.txt as file:line entries. (2) create a directory named archive and copy every .md file from the repo root into it. (3) create a file .env.example containing exactly: FOO=bar. (4) show the final directory tree in your reply.
```

## Execution summary

- Turn 1: wall **330.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **8** total, 8 chat calls
- Upstream results: 1 OK, 6 HTTP 429, 0 HTTP 502
- Git: 12 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 83.12s | — | — |
| req2 | POST /chat/completions | — | 429 | 0.07s | — | — |
| req3 | POST /chat/completions | — | 429 | 33.67s | — | 33.5 |
| req4 | POST /chat/completions | — | 429 | 33.17s | — | 33.0 |
| req5 | POST /chat/completions | — | 429 | 32.03s | — | 31.8 |
| req6 | POST /chat/completions | — | 429 | 33.55s | — | 33.4 |
| req7 | POST /chat/completions | — | 429 | 33.08s | — | 32.9 |
| req8 | POST /chat/completions | — | — | —s | — | 30.7 |

## Final verification

```json
{
 "todos_has_readme_line": false,
 "archive_created": false,
 "md_copied": 0,
 "md_list": [],
 "env_example": false
}
```

**Score justification:** checks 0/3 md_copied=0 [TIMEOUT] | t1=330.1s exit=-9 reqs=8 429=6 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification