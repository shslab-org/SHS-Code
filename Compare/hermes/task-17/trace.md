# task-17 — T2 GitHub repo + issue creation

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Using git and the GitHub CLI (gh, already installed and authenticated), create a NEW private GitHub repository named {REPO_NAME} under the authenticated account. Push all local branches to it. Then open an issue titled 'Benchmark audit' whose body lists every public function in calc.py with its one-line docstring. Report the repository URL and issue number.
```

## Execution summary

- Turn 1: wall **251.1s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **18** total, 6 chat calls
- Upstream results: 4 OK, 0 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.18s | — | — |
| req2 | GET /api/tags | — | 404 | 0.06s | — | — |
| req3 | GET /v1/props | — | 404 | 0.06s | — | — |
| req4 | GET /props | — | 404 | 0.06s | — | — |
| req5 | GET /version | — | 404 | 0.06s | — | — |
| req6 | GET /models | — | 200 | 0.06s | — | — |
| req7 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req8 | GET /v1/models | — | 404 | 0.06s | — | — |
| req9 | POST /api/show | — | 404 | 0.06s | — | — |
| req10 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req11 | GET /v1/models | — | 404 | 0.06s | — | — |
| req12 | POST /api/show | — | 404 | 0.06s | — | — |
| req13 | POST /chat/completions | — | — | —s | — | — |
| req14 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 15.84s | — | 34.0 |
| req15 | POST /chat/completions | — | — | —s | — | — |
| req16 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 34.0 |
| req17 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 73.08s | — | 34.0 |
| req18 | POST /chat/completions | — | 200 | 153.78s | — | 34.0 |

## Final verification

```json
{
 "note": "GitHub repo/issue verified via gh api post-hoc by harness"
}
```

**GitHub post-hoc check (gh api):**
```
{
 "repo_api": "{\"message\":\"Not Found\",\"documentation_url\":\"https://docs.github.com/rest/repos/repos#get-a-repository\",\"status\":\"404\"}",
 "issue_api": "{\"message\":\"Not Found\",\"documentation_url\":\"https://docs.github.com/rest/issues/issues#list-repository-issues\",\"status\":\"404\"}"
}
```

**Score justification:** no repo; 3 local commits | t1=251.1s exit=0 reqs=18 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification