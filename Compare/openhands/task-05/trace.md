# task-05 — M5 interruption + resume (kill at 70s, then continue)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
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
- Model requests (wire-level, via forensic proxy): **7** total, 7 chat calls
- Upstream results: 1 OK, 4 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.25s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.57s | — | 33.3 |
| req3 | POST /chat/completions | — | — | —s | — | 32.9 |
| req4 | POST /chat/completions | — | 429 | 28.18s | — | 27.9 |
| req5 | POST /chat/completions | — | 429 | 33.58s | — | 33.3 |
| req6 | POST /chat/completions | — | 200 | 51.47s | — | 32.9 |
| req7 | POST /chat/completions | — | — | —s | — | 15.4 |

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

**Score justification:** CH.md items=0 checked=0 done_marker=False | t1=70.0s exit=-9 reqs=7 429=4 tools~1; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification