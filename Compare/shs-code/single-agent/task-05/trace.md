# task-05 — M5 interruption + resume (kill at 70s, then continue)

- **Agent**: SHS Code v3.1.0 (single agent)
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 3/10

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
- Model requests (wire-level, via forensic proxy): **6** total, 6 chat calls
- Upstream results: 4 OK, 0 HTTP 429, 0 HTTP 502
- Git: 20 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req2 | POST /chat/completions | — | 200 | 8.51s | — | — |
| req3 | POST /chat/completions | — | 200 | 46.74s | — | 25.5 |
| req4 | POST /chat/completions | — | 200 | 39.96s | — | 12.7 |
| req5 | POST /chat/completions | — | 200 | 40.53s | — | 6.7 |
| req6 | POST /chat/completions | — | — | —s | — | 0.2 |

## Final verification

```json
{
 "ch_exists": true,
 "items_total": 5,
 "items_checked": 0,
 "done_marker": false,
 "all_done": false
}
```

**Score justification:** CH.md items=5 checked=0 done_marker=False | t1=70.0s exit=-9 reqs=6 429=0 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification