# task-20 — T5 combined release workflow

- **Agent**: SHS Code v3.1.0 (single agent)
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 3/10

## Canonical task prompt

**Turn 1:**

```
Release preparation: (1) bump the version to 0.2.0 in pyproject.toml. (2) append a section for 0.2.0 to CHANGELOG.md summarizing the repository state. (3) make the full test suite pass (fix the word_count bug). (4) create a branch named chore/release-0.2.0 and commit all changes there. (5) write RELEASE.md summarizing every step you performed.
```

## Execution summary

- Turn 1: wall **390.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **8** total, 8 chat calls
- Upstream results: 7 OK, 0 HTTP 429, 0 HTTP 502
- Git: 18 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 54.03s | — | — |
| req2 | POST /chat/completions | — | 200 | 18.68s | — | — |
| req3 | POST /chat/completions | — | 200 | 23.88s | — | 15.3 |
| req4 | POST /chat/completions | — | 200 | 158.89s | — | 25.4 |
| req5 | POST /chat/completions | — | 200 | 50.47s | — | — |
| req6 | POST /chat/completions | — | 200 | 22.69s | — | — |
| req7 | POST /chat/completions | — | 200 | 48.54s | — | 9.1 |
| req8 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "version_bumped": true,
 "changelog_updated": false,
 "release_md": false,
 "branch_created": false,
 "committed": false
}
```

**Score justification:** release workflow 1/5 [TIMEOUT] | t1=390.1s exit=-9 reqs=8 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification