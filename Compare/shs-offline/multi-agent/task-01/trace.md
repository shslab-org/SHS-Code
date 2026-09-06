# task-01 — M1 short-term context retention (2 turns, same session)

- **Agent**: SHS Code v3.1.0 OFFLINE (multi-agent, local 1B model)
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8397 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Read the files calc.py and textproc.py. Count the TOTAL number of function definitions (lines starting with 'def') across both files combined. Remember this number. Do not write it down anywhere yet. Reply with just the number.
```

**Turn 2:**

```
Without re-reading the files, write the total number of function definitions you counted in the previous step to a file named ANSWER.txt as plain digits only. Then reply with the number.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **2** total, 2 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 13 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | local-qwen3-1b | — | —s | — | — |
| req2 | POST /chat/completions | local-qwen3-1b | — | —s | — | — |

## Final verification

```json
{
 "answer": "",
 "correct": false,
 "note": "7 defs = 4 calc + 3 textproc; must be recalled without re-reading"
}
```

**Score justification:** answer file: '' [TIMEOUT] | t1=300.1s exit=-9 reqs=2 429=0 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification