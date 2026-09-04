# task-02 — M2 long-term memory across sessions (2 new sessions)

- **Agent**: OpenCode 1.18.27
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8391 forensic proxy)
- **Score**: 2/10

## Canonical task prompt

**Turn 1:**

```
Important project fact to remember for future sessions: this project's deployment port is 7331 and the preferred test runner is pytest. Store this in your persistent long-term memory. Reply DONE when stored.
```

**Turn 2:**

```
Without asking me any question: what is this project's deployment port? If you know it or can find it from what you previously stored, write ONLY the port number to a file named PORT.txt. If you truly cannot determine it, write UNKNOWN.
```

## Execution summary

- Turn 1: wall **38.5s**, exit `0`, finished
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **6** total, 6 chat calls
- Upstream results: 5 OK, 0 HTTP 429, 0 HTTP 502
- Git: 1 changed paths, 3 commits
- Visible tool calls in trace: 3

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 34.57s | — | 33.2 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 29.5 |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 78.76s | — | 34.0 |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 29.01s | — | 17.6 |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 22.2 |

## Tool calls (as visible in CLI output)

- `[82.23s]` tool:glob
- `[82.24s]` tool:grep
- `[111.73s]` tool:bash

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** PORT.txt='' | t1=38.5s exit=0 reqs=6 429=0 tools~3; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification