# task-17 — T2 GitHub repo + issue creation

- **Agent**: SHS Code v2.2.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Using git and the GitHub CLI (gh, already installed and authenticated), create a NEW private GitHub repository named {REPO_NAME} under the authenticated account. Push all local branches to it. Then open an issue titled 'Benchmark audit' whose body lists every public function in calc.py with its one-line docstring. Report the repository URL and issue number.
```

## Execution summary

- Turn 1: wall **390.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **4** total, 4 chat calls
- Upstream results: 3 OK, 0 HTTP 429, 0 HTTP 502
- Git: 5 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 146.86s | — | — |
| req2 | POST /chat/completions | — | 200 | 194.31s | — | — |
| req3 | POST /chat/completions | — | 200 | 27.6s | — | — |
| req4 | POST /chat/completions | — | — | —s | — | 6.4 |

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

**Score justification:** no repo; 3 local commits [TIMEOUT] | t1=390.1s exit=-9 reqs=4 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification