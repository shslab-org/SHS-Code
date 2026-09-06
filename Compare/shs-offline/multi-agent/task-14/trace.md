# task-14 — O4 test quality (thorough tests, no impl changes)

- **Agent**: SHS Code v3.1.0 OFFLINE (multi-agent, local 1B model)
- **Category**: Category 3: Output / Code Quality / Verification
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8397 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 7/10

## Canonical task prompt

**Turn 1:**

```
Write thorough pytest tests for reverse_words and capitalize_words in textproc.py, adding them to test_textproc.py. Cover edge cases: empty string, single word, multiple spaces, punctuation, and unicode like 'café'. Do NOT change the implementation. Run the tests you added.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **1** total, 1 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 12 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | local-qwen3-1b | — | —s | — | — |

## Final verification

```json
{
 "tests_for_reverse": true,
 "tests_for_capitalize": true,
 "edge_empty": true,
 "edge_unicode": false,
 "edge_multi_space": true,
 "impl_untouched": true,
 "count_new_tests": 6,
 "suite": "10p/2f"
}
```

**Score justification:** test-quality checks 5/6 new_tests=6 suite=10p/2f [TIMEOUT] | t1=300.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification