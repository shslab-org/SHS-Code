# task-16 — T1 git branch workflow

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 5/10

## Canonical task prompt

**Turn 1:**

```
Create a git branch named feat/logger. On that branch, implement logger.py with a function log(level, message) that appends a line like '2026-01-01T00:00:00 [INFO] message' (ISO timestamp) to app.log. Commit only logger.py on the branch with the message 'feat: add structured logger'. Then switch back to main. Report the branch name and the commit hash.
```

## Execution summary

- Turn 1: wall **330.2s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **11** total, 11 chat calls
- Upstream results: 7 OK, 3 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 15.79s | — | — |
| req2 | POST /chat/completions | — | 200 | 50.32s | — | 17.6 |
| req3 | POST /chat/completions | — | 429 | 1.28s | — | 1.2 |
| req4 | POST /chat/completions | — | 429 | 33.62s | — | 33.4 |
| req5 | POST /chat/completions | — | 200 | 54.24s | — | 33.0 |
| req6 | POST /chat/completions | — | 200 | 34.86s | — | 12.1 |
| req7 | POST /chat/completions | — | 200 | 51.83s | — | 11.2 |
| req8 | POST /chat/completions | — | 200 | 31.66s | — | — |
| req9 | POST /chat/completions | — | 200 | 23.19s | — | 2.2 |
| req10 | POST /chat/completions | — | 429 | 13.04s | — | 12.9 |
| req11 | POST /chat/completions | — | — | —s | — | 33.4 |

## Final verification

```json
{
 "branch_created": true,
 "commit_msg_conventional": true,
 "logger_implemented": false,
 "tests_still_pass": false,
 "main_unchanged": false
}
```

**Score justification:** git workflow 2/5 [TIMEOUT] | t1=330.2s exit=-9 reqs=11 429=3 tools~7

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification