# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: SHS Code v3.1.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
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
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **9** total, 9 chat calls
- Upstream results: 4 OK, 3 HTTP 429, 0 HTTP 502
- Git: 17 changed paths, 3 commits
- Visible tool calls in trace: 0
- Models observed on the wire: ['openai/gpt-oss-20b']

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 429 | 0.23s | — | — |
| req2 | POST /chat/completions | — | 429 | 33.64s | — | 33.4 |
| req3 | POST /chat/completions | — | 429 | 40.2s | — | 32.8 |
| req4 | POST /chat/completions | — | — | —s | — | 24.6 |
| req5 | POST /chat/completions | openai/gpt-oss-20b | 200 | 40.47s | — | — |
| req6 | POST /chat/completions | — | 200 | 40.84s | — | — |
| req7 | POST /chat/completions | — | 200 | 4.4s | — | — |
| req8 | POST /chat/completions | — | 200 | 43.13s | — | 29.6 |
| req9 | POST /chat/completions | — | — | —s | — | 20.4 |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) [TIMEOUT] | t1=300.1s exit=-9 reqs=9 429=3 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification