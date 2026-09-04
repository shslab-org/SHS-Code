# task-12 — O2 bug fix quality (word_count hidden tests)

- **Agent**: SHS Code v2.2.0 (single agent)
- **Category**: Category 3: Output / Code Quality / Verification
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 7/10

## Canonical task prompt

**Turn 1:**

```
The word_count function in textproc.py is broken: it splits on single spaces so punctuation attached to words and consecutive spaces miscount it. Fix it so words are sequences of non-whitespace characters with surrounding punctuation stripped (e.g. 'Hello,  world!!' -> 2, 'a...b' -> 2, '' -> 0, '!@#$%' -> 0). Add regression tests to test_textproc.py.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 7 OK, 1 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 31.72s | — | — |
| req2 | POST /chat/completions | — | 200 | 24.99s | — | 2.3 |
| req3 | POST /chat/completions | — | 429 | 11.42s | — | 11.3 |
| req4 | POST /chat/completions | — | 200 | 36.13s | — | 32.9 |
| req5 | POST /chat/completions | — | 200 | 42.29s | — | 30.7 |
| req6 | POST /chat/completions | — | 200 | 73.0s | — | 22.4 |
| req7 | POST /chat/completions | — | 200 | 33.04s | — | — |
| req8 | POST /chat/completions | — | 200 | 15.22s | — | 0.9 |
| req9 | POST /chat/completions | — | — | —s | — | 19.7 |

## Final verification

```json
{
 "hidden_cases": {
  "'Hello,  world!!'": true,
  "'a...b'": false,
  "''": true,
  "'   '": true,
  "'one two three'": true,
  "'word.'": true,
  "'  leading'": true,
  "'trailing  '": true,
  "'multiple   spaces here'": true,
  "'!@#$%'": true,
  "\"don't stop\"": true
 },
 "all_pass": false,
 "regression_tests_added": true
}
```

**Score justification:** hidden word_count tests 10/11 regressions=True [TIMEOUT] | t1=300.1s exit=-9 reqs=9 429=1 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification