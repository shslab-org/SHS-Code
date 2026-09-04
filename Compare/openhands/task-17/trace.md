# task-17 — T2 GitHub repo + issue creation

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 6/10

## Canonical task prompt

**Turn 1:**

```
Using git and the GitHub CLI (gh, already installed and authenticated), create a NEW private GitHub repository named {REPO_NAME} under the authenticated account. Push all local branches to it. Then open an issue titled 'Benchmark audit' whose body lists every public function in calc.py with its one-line docstring. Report the repository URL and issue number.
```

## Execution summary

- Turn 1: wall **390.2s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **12** total, 12 chat calls
- Upstream results: 8 OK, 3 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 8.64s | — | — |
| req2 | POST /chat/completions | — | 200 | 32.07s | — | 24.7 |
| req3 | POST /chat/completions | — | 429 | 26.84s | — | 26.6 |
| req4 | POST /chat/completions | — | 429 | 33.51s | — | 33.3 |
| req5 | POST /chat/completions | — | 200 | 44.11s | — | 32.8 |
| req6 | POST /chat/completions | — | 200 | 57.27s | — | 22.3 |
| req7 | POST /chat/completions | — | 429 | 0.12s | — | — |
| req8 | POST /chat/completions | — | 200 | 47.48s | — | 33.5 |
| req9 | POST /chat/completions | — | 200 | 34.44s | — | 19.9 |
| req10 | POST /chat/completions | — | 200 | 26.66s | — | 15.8 |
| req11 | POST /chat/completions | — | 200 | 44.89s | — | 22.5 |
| req12 | POST /chat/completions | — | — | —s | — | 10.5 |

## Final verification

```json
{
 "note": "GitHub repo/issue verified via gh api post-hoc by harness"
}
```

**GitHub post-hoc check (gh api):**
```
{
 "repo_api": "true\nhttps://github.com/shslab-org/bench-openhands",
 "issue_api": ""
}
```

**Score justification:** repo created; issue missing; 3 local commits [TIMEOUT] | t1=390.2s exit=-9 reqs=12 429=3 tools~8

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification