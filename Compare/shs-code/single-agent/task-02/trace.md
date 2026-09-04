# task-02 — M2 long-term memory across sessions (2 new sessions)

- **Agent**: SHS Code v2.2.0 (single agent)
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8394 forensic proxy)
- **Score**: 7/10

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
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **12** total, 12 chat calls
- Upstream results: 10 OK, 0 HTTP 429, 0 HTTP 502
- Git: 11 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 31.88s | — | — |
| req2 | POST /chat/completions | — | 200 | 18.47s | — | 2.1 |
| req3 | POST /chat/completions | — | 200 | 18.39s | — | 17.6 |
| req4 | POST /chat/completions | — | 200 | 44.59s | — | 33.2 |
| req5 | POST /chat/completions | — | 200 | 35.38s | — | 22.7 |
| req6 | POST /chat/completions | — | 200 | 29.28s | — | 21.3 |
| req7 | POST /chat/completions | — | 200 | 61.46s | — | 26.0 |
| req8 | POST /chat/completions | — | — | —s | — | — |
| req9 | POST /chat/completions | — | 200 | 39.14s | — | 33.4 |
| req10 | POST /chat/completions | — | 200 | 30.53s | — | 28.3 |
| req11 | POST /chat/completions | — | 200 | 34.07s | — | 31.7 |
| req12 | POST /chat/completions | — | — | —s | — | 31.6 |

## Final verification

```json
{
 "answer": "7331",
 "correct": true
}
```

**Score justification:** port recalled in a NEW session (persistent long-term memory) [TIMEOUT] | t1=240.1s exit=-9 reqs=12 429=0 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification