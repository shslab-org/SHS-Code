# task-20 — T5 combined release workflow

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Release preparation: (1) bump the version to 0.2.0 in pyproject.toml. (2) append a section for 0.2.0 to CHANGELOG.md summarizing the repository state. (3) make the full test suite pass (fix the word_count bug). (4) create a branch named chore/release-0.2.0 and commit all changes there. (5) write RELEASE.md summarizing every step you performed.
```

## Execution summary

- Turn 1: wall **390.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **12** total, 12 chat calls
- Upstream results: 0 OK, 12 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.62s | — | 33.4 |
| req3 | POST /chat/completions | — | 429 | 33.0s | — | 32.7 |
| req4 | POST /chat/completions | — | 429 | 25.98s | — | 25.7 |
| req5 | POST /chat/completions | — | 429 | 33.55s | — | 33.3 |
| req6 | POST /chat/completions | — | 429 | 33.2s | — | 32.9 |
| req7 | POST /chat/completions | — | 429 | 18.01s | — | 17.7 |
| req8 | POST /chat/completions | — | 429 | 33.51s | — | 33.3 |
| req9 | POST /chat/completions | — | 429 | 33.06s | — | 32.8 |
| req10 | POST /chat/completions | — | 429 | 1.96s | — | 1.7 |
| req11 | POST /chat/completions | — | 429 | 33.64s | — | 33.4 |
| req12 | POST /chat/completions | — | 429 | 33.08s | — | 32.8 |

## Final verification

```json
{
 "version_bumped": false,
 "changelog_updated": false,
 "release_md": false,
 "branch_created": false,
 "committed": false
}
```

**Score justification:** release workflow 0/5 [TIMEOUT] | t1=390.1s exit=-9 reqs=12 429=12 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification