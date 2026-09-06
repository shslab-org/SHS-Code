# task-05 — M5 interruption + resume (kill at 70s, then continue)

- **Agent**: Hermes Agent v0.21.0
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8393 forensic proxy)
- **Score**: 1/10

## Canonical task prompt

**Turn 1:**

```
Create CH.md containing exactly these 5 checklist items, all unchecked:
1. add strip_punct(s) to textproc.py (strips non-alphanumeric characters)
2. add test_strip_punct to test_textproc.py
3. create utils/dates.py with today_iso() returning today as YYYY-MM-DD
4. update README.md with a module list
5. run the full test suite
Then execute the items in order, marking each with [x] in CH.md as you complete it. When all 5 are done and checked, write DONE.txt containing DONE.
```

**Turn 2:**

```
Continue your interrupted checklist task from where you left off. Complete every remaining item, checking each off in CH.md, and write DONE.txt containing DONE when finished.
```

## Execution summary

- Turn 1: wall **70.0s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **66** total, 8 chat calls
- Upstream results: 3 OK, 5 HTTP 429, 0 HTTP 502
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
| req31 | POST /chat/completions | — | 429 | 31.48s | — | 31.2 |
| req32 | POST /chat/completions | — | — | —s | — | 27.7 |
| req33 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req34 | GET /api/tags | — | 404 | 0.06s | — | — |
| req35 | GET /v1/props | — | 404 | 0.06s | — | — |
| req36 | GET /props | — | 404 | 0.06s | — | — |
| req37 | GET /version | — | 404 | 0.06s | — | — |
| req38 | GET /api/v1/models | — | 404 | 0.06s | — | — |
| req39 | GET /api/tags | — | 404 | 0.06s | — | — |
| req40 | GET /v1/props | — | 404 | 0.06s | — | — |
| … | (26 more in proxy.jsonl) | | | | | |

## Final verification

```json
{
 "ch_exists": false,
 "items_total": 0,
 "items_checked": 0,
 "done_marker": false,
 "all_done": false
}
```

**Score justification:** CH.md items=0 checked=0 done_marker=False | t1=70.0s exit=-9 reqs=66 429=5 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification