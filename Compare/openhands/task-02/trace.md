# task-02 — M2 long-term memory across sessions (2 new sessions)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
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
- Model requests (wire-level, via forensic proxy): **13** total, 13 chat calls
- Upstream results: 1 OK, 10 HTTP 429, 0 HTTP 502
- Git: 8 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 7.38s | — | — |
| req2 | POST /chat/completions | — | 429 | 26.77s | — | 26.5 |
| req3 | POST /chat/completions | — | 429 | 33.64s | — | 33.4 |
| req4 | POST /chat/completions | — | 429 | 33.21s | — | 33.0 |
| req5 | POST /chat/completions | — | 429 | 26.0s | — | 25.7 |
| req6 | POST /chat/completions | — | 429 | 33.62s | — | 33.4 |
| req7 | POST /chat/completions | — | 429 | 33.26s | — | 33.0 |
| req8 | POST /chat/completions | — | — | —s | — | 17.7 |
| req9 | POST /chat/completions | — | 429 | 31.99s | — | 31.7 |
| req10 | POST /chat/completions | — | 429 | 33.55s | — | 33.3 |
| req11 | POST /chat/completions | — | 429 | 33.14s | — | 32.9 |
| req12 | POST /chat/completions | — | 429 | 25.99s | — | 25.7 |
| req13 | POST /chat/completions | — | — | —s | — | 33.4 |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** PORT.txt='' [TIMEOUT] | t1=240.1s exit=-9 reqs=13 429=10 tools~1; t2=150.1s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification