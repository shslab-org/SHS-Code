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

- Turn 1: wall **240.1s**, exit `-9`, KILLED (timeout)
- Turn 2: wall **150.1s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **14** total, 14 chat calls
- Upstream results: 0 OK, 11 HTTP 429, 0 HTTP 502
- Git: 9 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 0.19s | — | — |
| req2 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 33.2 |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 33.47s | — | 34.0 |
| req4 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 66.01s | — | 34.0 |
| req5 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.59s | — | 34.0 |
| req6 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 63.09s | — | 34.0 |
| req7 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 26.03s | — | 25.7 |
| req8 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 16.8 |
| req9 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | 31.8 |
| req10 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 32.0s | — | 34.0 |
| req11 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.38s | — | 34.0 |
| req12 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 66.01s | — | 34.0 |
| req13 | POST /chat/completions | minimaxai/minimax-m3 | 429 | 65.73s | — | 34.0 |
| req14 | POST /chat/completions | minimaxai/minimax-m3 | — | —s | — | — |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** PORT.txt='' [TIMEOUT] | t1=240.1s exit=-9 reqs=14 429=11 tools~0; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification