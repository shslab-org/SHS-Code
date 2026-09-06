# task-19 — T4 terminal + filesystem operations

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Do these steps in order: (1) find every TODO comment in the repository and write them to TODOS.txt as file:line entries. (2) create a directory named archive and copy every .md file from the repo root into it. (3) create a file .env.example containing exactly: FOO=bar. (4) show the final directory tree in your reply.
```

## Execution summary

- Turn 1: wall **330.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **11** total, 11 chat calls
- Upstream results: 0 OK, 10 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.61s | — | 33.3 |
| req3 | POST /chat/completions | — | 429 | 33.2s | — | 33.0 |
| req4 | POST /chat/completions | — | 429 | 25.99s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 33.54s | — | 33.3 |
| req6 | POST /chat/completions | — | 429 | 33.09s | — | 32.8 |
| req7 | POST /chat/completions | — | 429 | 17.99s | — | 17.7 |
| req8 | POST /chat/completions | — | 429 | 33.64s | — | 33.4 |
| req9 | POST /chat/completions | — | 429 | 33.18s | — | 32.9 |
| req10 | POST /chat/completions | — | 429 | 2.0s | — | 1.7 |
| req11 | POST /chat/completions | — | — | —s | — | 33.3 |

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

**Score justification:** checks 0/3 md_copied=0 [TIMEOUT] | t1=330.1s exit=-9 reqs=11 429=10 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification