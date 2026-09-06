# task-12 — O2 bug fix quality (word_count hidden tests)

- **Agent**: SHS Code v3.1.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 3: Output / Code Quality / Verification
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
- **Score**: 3/10

## Canonical task prompt

**Turn 1:**

```
The word_count function in textproc.py is broken: it splits on single spaces so punctuation attached to words and consecutive spaces miscount it. Fix it so words are sequences of non-whitespace characters with surrounding punctuation stripped (e.g. 'Hello,  world!!' -> 2, 'a...b' -> 2, '' -> 0, '!@#$%' -> 0). Add regression tests to test_textproc.py.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **2** total, 2 chat calls
- Upstream results: 1 OK, 0 HTTP 429, 0 HTTP 502
- Git: 12 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 141.33s | — | — |
| req2 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "hidden_cases": {
  "'Hello,  world!!'": false,
  "'a...b'": false,
  "''": false,
  "'   '": false,
  "'one two three'": true,
  "'word.'": true,
  "'  leading'": false,
  "'trailing  '": false,
  "'multiple   spaces here'": false,
  "'!@#$%'": false,
  "\"don't stop\"": true
 },
 "all_pass": false,
 "regression_tests_added": true
}
```

**Score justification:** hidden word_count tests 3/11 regressions=True [TIMEOUT] | t1=300.1s exit=-9 reqs=2 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification