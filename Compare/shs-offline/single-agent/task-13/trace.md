# task-13 — O3 refactor (class-based Calculator, API compat)

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 3: Output / Code Quality / Verification
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 4/10

## Canonical task prompt

**Turn 1:**

```
Refactor calc.py so the arithmetic lives in a Calculator class with add, sub, mul, div methods, while KEEPING the existing module-level functions add/sub/mul/div as thin wrappers so the existing tests pass unchanged. Run the test suite to confirm.
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
 "has_class": false,
 "has_methods": true,
 "module_fns_wrapped": true,
 "suite": "10p/2f",
 "tests_unchanged_pass": false
}
```

**Score justification:** class=False compat=False suite=10p/2f [TIMEOUT] | t1=300.1s exit=-9 reqs=1 429=0 tools~0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification