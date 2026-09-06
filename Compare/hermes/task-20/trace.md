# task-20 — T5 combined release workflow

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 4: Tools / GitHub / MCP / Skills / Integrations
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Release preparation: (1) bump the version to 0.2.0 in pyproject.toml. (2) append a section for 0.2.0 to CHANGELOG.md summarizing the repository state. (3) make the full test suite pass (fix the word_count bug). (4) create a branch named chore/release-0.2.0 and commit all changes there. (5) write RELEASE.md summarizing every step you performed.
```

## Execution summary

- Turn 1: wall **74.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **32** total, 3 chat calls
- Upstream results: 1 OK, 3 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | GET /api/v1/models | — | 404 | 0.17s | — | — |
| req2 | GET /api/tags | — | 404 | 0.06s | — | — |
| req3 | GET /v1/props | — | 404 | 0.06s | — | — |
| req4 | GET /props | — | 404 | 0.06s | — | — |
| req5 | GET /version | — | 404 | 0.06s | — | — |
| req6 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req7 | GET /api/tags | — | 404 | 0.06s | — | — |
| req8 | GET /v1/props | — | 404 | 0.06s | — | — |
| req9 | GET /props | — | 404 | 0.06s | — | — |
| req10 | GET /version | — | 404 | 0.06s | — | — |
| req11 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req12 | GET /api/tags | — | 404 | 0.06s | — | — |
| req13 | GET /v1/props | — | 404 | 0.06s | — | — |
| req14 | GET /props | — | 404 | 0.06s | — | — |
| req15 | GET /version | — | 404 | 0.06s | — | — |
| req16 | GET /models | — | 200 | 0.06s | — | — |
| req17 | POST /api/show | — | 404 | 0.06s | — | — |
| req18 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req19 | GET /api/tags | — | 404 | 0.06s | — | — |
| req20 | GET /v1/props | — | 404 | 0.06s | — | — |
| req21 | GET /props | — | 404 | 0.06s | — | — |
| req22 | GET /version | — | 404 | 0.06s | — | — |
| req23 | GET /v1/models/minimaxai/minimax-m3 | — | 404 | 0.06s | — | — |
| req24 | GET /v1/models | — | 404 | 0.06s | — | — |
| req25 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req26 | GET /api/tags | — | 404 | 0.06s | — | — |
| req27 | GET /v1/props | — | 404 | 0.06s | — | — |
| req28 | GET /props | — | 404 | 0.06s | — | — |
| req29 | GET /version | — | 404 | 0.06s | — | — |
| req30 | POST /chat/completions | — | 429 | 0.14s | — | — |
| req31 | POST /chat/completions | — | 429 | 31.27s | — | 31.0 |
| req32 | POST /chat/completions | — | 429 | 29.21s | — | 28.9 |

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

**Score justification:** release workflow 0/5 | t1=74.0s exit=0 reqs=32 429=3 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification