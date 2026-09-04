# task-25 — R5 model switch mid-conversation (2 turns)

- **Agent**: OpenCode 1.18.27
- **Category**: Category 5: Reliability / Rate Limit / Recovery
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8391 forensic proxy)
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

- Turn 1: wall **275.1s**, exit `1`, finished
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **14** total, 14 chat calls
- Upstream results: 4 OK, 9 HTTP 429, 0 HTTP 502
- Git: 1 changed paths, 3 commits
- Visible tool calls in trace: 2
- Models observed on the wire: ['minimaxai/minimax-m3', 'openai/gpt-oss-20b']

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.19s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 33.0 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 33.23s | — | 34.0 |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 66.0s | — | 34.0 |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.61s | — | 34.0 |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 63.62s | — | 34.0 |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 24.71s | — | 24.5 |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 15.8s | — | 15.6 |
| req9 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.62s | — | 0.4 |
| req10 | POST /chat/completions | openai/gpt-oss-20b | — | —s | — | 30.9 |
| req11 | POST /chat/completions | openai/gpt-oss-20b | 200 | 77.86s | — | 34.0 |
| req12 | POST /chat/completions | openai/gpt-oss-20b | 200 | 26.6s | — | 18.0 |
| req13 | POST /chat/completions | openai/gpt-oss-20b | 200 | 28.35s | — | 25.3 |
| req14 | POST /chat/completions | openai/gpt-oss-20b | — | —s | — | 30.8 |

## Tool calls (as visible in CLI output)

- `[109.91s]` tool:glob
- `[138.4s]` tool:read

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) | t1=275.1s exit=1 reqs=14 429=9 tools~2; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification