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

- Turn 1: wall **275.1s**, exit `1`, finished
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 0 OK, 9 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.2s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 33.1 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 33.32s | — | 34.0 |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 66.02s | — | 34.0 |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.55s | — | 34.0 |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 63.53s | — | 34.0 |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 25.03s | — | 24.8 |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 16.07s | — | 15.9 |
| req9 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 1.45s | — | 1.2 |

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

**Score justification:** repo created; issue missing; 3 local commits | t1=275.1s exit=1 reqs=9 429=9 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification