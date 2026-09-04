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
- Upstream results: 10 OK, 1 HTTP 429, 0 HTTP 502
- Git: 0 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 8.87s | — | — |
| req2 | POST /chat/completions | — | 200 | 33.59s | — | 24.5 |
| req3 | POST /chat/completions | — | 429 | 25.09s | — | 24.9 |
| req4 | POST /chat/completions | — | 200 | 42.69s | — | 33.4 |
| req5 | POST /chat/completions | — | 200 | 33.17s | — | 24.6 |
| req6 | POST /chat/completions | — | 200 | 37.64s | — | 25.4 |
| req7 | POST /chat/completions | — | 200 | 24.04s | — | 21.7 |
| req8 | POST /chat/completions | — | 200 | 35.79s | — | 31.6 |
| req9 | POST /chat/completions | — | 200 | 37.95s | — | 29.7 |
| req10 | POST /chat/completions | — | 200 | 40.79s | — | 25.7 |
| req11 | POST /chat/completions | — | 200 | 27.26s | — | 18.9 |
| req12 | POST /chat/completions | — | — | —s | — | 25.5 |

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

**Score justification:** release workflow 0/5 [TIMEOUT] | t1=390.1s exit=-9 reqs=12 429=1 tools~10

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification