# task-17 — T2 GitHub repo + issue creation

- **Agent**: SHS Code v2.2.0 (single agent)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 10/10

## Canonical task prompt

**Turn 1:**

```
Using git and the GitHub CLI (gh, already installed and authenticated), create a NEW private GitHub repository named {REPO_NAME} under the authenticated account. Push all local branches to it. Then open an issue titled 'Benchmark audit' whose body lists every public function in calc.py with its one-line docstring. Report the repository URL and issue number.
```

## Execution summary

- Turn 1: wall **326.1s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **8** total, 8 chat calls
- Upstream results: 8 OK, 0 HTTP 429, 0 HTTP 502
- Git: 4 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 38.87s | — | — |
| req2 | POST /chat/completions | — | 200 | 19.56s | — | — |
| req3 | POST /chat/completions | — | 200 | 28.96s | — | 13.5 |
| req4 | POST /chat/completions | — | 200 | 25.91s | — | 18.5 |
| req5 | POST /chat/completions | — | 200 | 58.39s | — | 21.7 |
| req6 | POST /chat/completions | — | 200 | 64.23s | — | — |
| req7 | POST /chat/completions | — | 200 | 19.65s | — | — |
| req8 | POST /chat/completions | — | 200 | 58.2s | — | 13.8 |

## Final verification

```json
{
 "note": "GitHub repo/issue verified via gh api post-hoc by harness"
}
```

**GitHub post-hoc check (gh api):**
```
{
 "repo_api": "true\nhttps://github.com/shslab-org/bench-shs-single",
 "issue_api": "1\nBenchmark audit"
}
```

**Score justification:** repo created AND issue opened with function list; 3 local commits | t1=326.1s exit=0 reqs=8 429=0 tools~1

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification