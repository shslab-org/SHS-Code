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

- Turn 1: wall **390.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **12** total, 12 chat calls
- Upstream results: 1 OK, 10 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.53s | — | 33.3 |
| req3 | POST /chat/completions | — | 429 | 33.16s | — | 32.9 |
| req4 | POST /chat/completions | — | 200 | 29.04s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 30.35s | — | 30.1 |
| req6 | POST /chat/completions | — | 429 | 33.53s | — | 33.3 |
| req7 | POST /chat/completions | — | 429 | 33.17s | — | 32.9 |
| req8 | POST /chat/completions | — | 429 | 26.02s | — | 25.7 |
| req9 | POST /chat/completions | — | 429 | 33.61s | — | 33.4 |
| req10 | POST /chat/completions | — | 429 | 33.2s | — | 32.9 |
| req11 | POST /chat/completions | — | 429 | 17.98s | — | 17.7 |
| req12 | POST /chat/completions | — | — | —s | — | 33.3 |

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

**Score justification:** repo created; issue missing; 3 local commits [TIMEOUT] | t1=390.1s exit=-9 reqs=12 429=10 tools~1

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification