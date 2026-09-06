# task-18 — T3 MCP tool usage (get_time)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Use the MCP tool get_time provided by the configured MCP server 'bench' to obtain the current server time, and write exactly what the tool returns to a file named TIME.txt. If the MCP server is unavailable, write MCP-UNAVAILABLE instead.
```

## Execution summary

- Turn 1: wall **330.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **11** total, 11 chat calls
- Upstream results: 2 OK, 8 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.64s | — | 33.4 |
| req3 | POST /chat/completions | — | 429 | 33.31s | — | 33.0 |
| req4 | POST /chat/completions | — | 429 | 25.94s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 33.63s | — | 33.4 |
| req6 | POST /chat/completions | — | 429 | 33.16s | — | 32.9 |
| req7 | POST /chat/completions | — | 429 | 18.0s | — | 17.7 |
| req8 | POST /chat/completions | — | 429 | 33.55s | — | 33.3 |
| req9 | POST /chat/completions | — | 200 | 36.24s | — | 33.0 |
| req10 | POST /chat/completions | — | 200 | 32.49s | — | 30.7 |
| req11 | POST /chat/completions | — | — | —s | — | 32.1 |

## Final verification

```json
{
 "time_file": "",
 "nonempty": false,
 "plausible": false
}
```

**Score justification:** no TIME.txt content [TIMEOUT] | t1=330.1s exit=-9 reqs=11 429=8 tools~2

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification