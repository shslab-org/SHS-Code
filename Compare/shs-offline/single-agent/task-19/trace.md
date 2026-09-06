# task-19 — T4 terminal + filesystem operations

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Do these steps in order: (1) find every TODO comment in the repository and write them to TODOS.txt as file:line entries. (2) create a directory named archive and copy every .md file from the repo root into it. (3) create a file .env.example containing exactly: FOO=bar. (4) show the final directory tree in your reply.
```

## Execution summary

- Turn 1: wall **330.1s**, exit `-9`, KILLED (timeout)
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
 "todos_has_readme_line": false,
 "archive_created": false,
 "md_copied": 0,
 "md_list": [],
 "env_example": false
}
```

**Score justification:** checks 0/3 md_copied=0 [TIMEOUT] | t1=330.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification