# task-17 — T2 GitHub repo + issue creation

- **Agent**: OpenCode 1.18.27
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8391 forensic proxy)
- **Score**: 6/10

## Canonical task prompt

**Turn 1:**

```
Using git and the GitHub CLI (gh, already installed and authenticated), create a NEW private GitHub repository named {REPO_NAME} under the authenticated account. Push all local branches to it. Then open an issue titled 'Benchmark audit' whose body lists every public function in calc.py with its one-line docstring. Report the repository URL and issue number.
```

## Execution summary

- Turn 1: wall **352.6s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **8** total, 8 chat calls
- Upstream results: 7 OK, 1 HTTP 429, 0 HTTP 502
- Git: 1 changed paths, 3 commits
- Visible tool calls in trace: 7

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 135.72s | — | 33.0 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.24s | — | — |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 47.38s | — | 31.3 |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 22.72s | — | 16.8 |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 53.84s | — | 27.9 |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 50.47s | — | 3.4 |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 29.78s | — | — |

## Tool calls (as visible in CLI output)

- `[139.16s]` tool:todowrite
- `[190.4s]` tool:bash
- `[213.31s]` tool:bash
- `[267.37s]` tool:read
- `[271.93s]` tool:bash
- `[322.49s]` tool:todowrite
- `[351.96s]` tool:write

## Final verification

```json
{
 "note": "GitHub repo/issue verified via gh api post-hoc by harness"
}
```

**GitHub post-hoc check (gh api):**
```
{
 "repo_api": "true\nhttps://github.com/shslab-org/bench-opencode",
 "issue_api": ""
}
```

**Score justification:** repo created; issue missing; 3 local commits | t1=352.6s exit=0 reqs=8 429=1 tools~7

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification