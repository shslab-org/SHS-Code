# task-02 — M2 long-term memory across sessions (2 new sessions)

- **Agent**: OpenHands CLI 1.13.1
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8392 forensic proxy)
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
- Turn 2: wall **120.0s**, exit `0`, finished
- Model requests (wire-level, via forensic proxy): **11** total, 11 chat calls
- Upstream results: 5 OK, 5 HTTP 429, 0 HTTP 502
- Git: 2 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | — | 200 | 22.36s | — | — |
| req2 | POST /chat/completions | — | 200 | 18.84s | — | 11.5 |
| req3 | POST /chat/completions | — | 429 | 26.9s | — | 26.7 |
| req4 | POST /chat/completions | — | 429 | 33.54s | — | 33.3 |
| req5 | POST /chat/completions | — | 429 | 33.1s | — | 32.9 |
| req6 | POST /chat/completions | — | 429 | 25.99s | — | 25.7 |
| req7 | POST /chat/completions | — | 429 | 33.62s | — | 33.4 |
| req8 | POST /chat/completions | — | — | —s | — | 32.8 |
| req9 | POST /chat/completions | — | 200 | 41.5s | — | 31.8 |
| req10 | POST /chat/completions | — | 200 | 28.04s | — | 24.2 |
| req11 | POST /chat/completions | — | 200 | 33.34s | — | 30.1 |

## Final verification

```json
{
 "answer": "7331",
 "correct": true
}
```

**Score justification:** port recalled in a NEW session (persistent long-term memory) [TIMEOUT] | t1=240.1s exit=-9 reqs=11 429=5 tools~5; t2=120.0s exit=0

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification