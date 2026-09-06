# task-17 — T2 GitHub repo + issue creation

- **Agent**: SHS Code v3.1.0 (single agent)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 7/10

## Canonical task prompt

**Turn 1:**

```
Using git and the GitHub CLI (gh, already installed and authenticated), create a NEW private GitHub repository named {REPO_NAME} under the authenticated account. Push all local branches to it. Then open an issue titled 'Benchmark audit' whose body lists every public function in calc.py with its one-line docstring. Report the repository URL and issue number.
```

## Execution summary

- Turn 1: wall **390.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **11** total, 11 chat calls
- Upstream results: 10 OK, 0 HTTP 429, 0 HTTP 502
- Git: 18 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 50.38s | — | — |
| req2 | POST /chat/completions | — | 200 | 13.98s | — | — |
| req3 | POST /chat/completions | — | 200 | 30.15s | — | 18.7 |
| req4 | POST /chat/completions | — | 200 | 33.58s | — | 22.6 |
| req5 | POST /chat/completions | — | 200 | 47.3s | — | 22.4 |
| req6 | POST /chat/completions | — | 200 | 29.58s | — | 6.7 |
| req7 | POST /chat/completions | — | 200 | 37.07s | — | 10.8 |
| req8 | POST /chat/completions | — | 200 | 38.39s | — | 6.7 |
| req9 | POST /chat/completions | — | 200 | 19.51s | — | 1.8 |
| req10 | POST /chat/completions | — | 200 | 46.59s | — | 15.2 |
| req11 | POST /chat/completions | — | — | —s | — | 2.1 |

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
 "issue_api": "2\nBenchmark audit"
}
```

**Score justification:** repo created AND issue opened with function list; 3 local commits [TIMEOUT] | t1=390.1s exit=-9 reqs=11 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification