# task-12 — O2 bug fix quality (word_count hidden tests)

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 3: Output / Code Quality / Verification
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 3/10

## Canonical task prompt

**Turn 1:**

```
The word_count function in textproc.py is broken: it splits on single spaces so punctuation attached to words and consecutive spaces miscount it. Fix it so words are sequences of non-whitespace characters with surrounding punctuation stripped (e.g. 'Hello,  world!!' -> 2, 'a...b' -> 2, '' -> 0, '!@#$%' -> 0). Add regression tests to test_textproc.py.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **1** total, 1 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 18 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | local-qwen3-1b | — | —s | — | — |

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

**Score justification:** hidden word_count tests 3/11 regressions=True [TIMEOUT] | t1=300.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification