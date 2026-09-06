# task-18 — T3 MCP tool usage (get_time)

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Use the MCP tool get_time provided by the configured MCP server 'bench' to obtain the current server time, and write exactly what the tool returns to a file named TIME.txt. If the MCP server is unavailable, write MCP-UNAVAILABLE instead.
```

## Execution summary

- Turn 1: wall **330.2s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **1** total, 1 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 19 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | local-qwen3-1b | — | —s | — | — |

## Final verification

```json
{
 "time_file": "",
 "nonempty": false,
 "plausible": false
}
```

**Score justification:** no TIME.txt content [TIMEOUT] | t1=330.2s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification