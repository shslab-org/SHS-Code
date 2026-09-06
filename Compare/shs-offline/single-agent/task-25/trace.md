# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: SHS Code v3.1.0 OFFLINE (single agent, local 1B model)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server on :8090 via forensic proxy :8396 (offline round; random-init create-tiny-model artifact, see README)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Read calc.py. Which function performs safe division (raising on zero divisor)? Remember its exact name. Reply with just the function name.
```

**Turn 2:**

```
Write the name of the function you identified in the previous turn to Write the name of the function you identified in the previous turn to a file named SAFEFUNC.txt (create it). Reply with the function name.
```

## Execution summary

- Turn 1: wall **300.1s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **2** total, 2 chat calls
- Upstream results: 0 OK, 0 HTTP 429, 0 HTTP 502
- Git: 19 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: ['openai/local-qwen3-1b']

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | — | —s | — | — |
| req2 | POST /chat/completions | openai/local-qwen3-1b | — | —s | — | — |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) [TIMEOUT] | t1=300.1s exit=-9 reqs=2 429=0 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification