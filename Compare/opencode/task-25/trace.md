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

- Turn 1: wall **300.2s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **14** total, 14 chat calls
- Upstream results: 3 OK, 9 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 2
- Models observed on the wire: ['minimaxai/minimax-m3', 'openai/gpt-oss-20b']

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.21s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 33.1 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 33.3s | — | 34.0 |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.99s | — | 34.0 |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.93s | — | 34.0 |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 63.83s | — | 34.0 |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 25.88s | — | 24.6 |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 32.84s | — | 32.6 |
| req9 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 31.65s | — | 31.4 |
| req10 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 29.0 |
| req11 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req12 | POST /chat/completions | openai/gpt-oss-20b | 429 | 40.25s | — | 34.0 |
| req13 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 79.52s | — | 34.0 |
| req14 | POST /chat/completions | openai/gpt-oss-20b | 200 | 66.32s | — | 34.0 |

## Tool calls (as visible in CLI output)

- `[207.83s]` tool:read
- `[82.73s]` tool:glob

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** SAFEFUNC.txt='' (model did switch, context lost/timeout) [TIMEOUT] | t1=300.2s exit=-9 reqs=14 429=9 tools~2; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification