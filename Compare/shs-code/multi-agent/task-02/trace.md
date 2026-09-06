# task-02 — M2 long-term memory across sessions (2 new sessions)

- **Agent**: SHS Code v3.1.0 (multi-agent: PM/Architect/Engineer/QA)
- **Category**: Category 1: Memory & Persistent Work State
- **Model**: minimaxai/minimax-m3 via NVIDIA NIM (http://127.0.0.1:8395 forensic proxy)
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
- Turn 2: wall **150.0s**, exit `-9`, KILLED (timeout)
- Model requests (wire-level, via forensic proxy): **4** total, 4 chat calls
- Upstream results: 2 OK, 0 HTTP 429, 0 HTTP 502
- Git: 13 changed paths, 3 commits
- Visible tool calls in trace: 0

## Model request log (wire-level)

| # | method/path | model | status | dur | injected | paced-wait |
|---|-------------|-------|--------|-----|----------|------------|
| req1 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 70.11s | — | — |
| req2 | POST /chat/completions | — | — | —s | — | — |
| req3 | POST /chat/completions | minimaxai/minimax-m3 | 200 | 74.44s | — | — |
| req4 | POST /chat/completions | — | — | —s | — | — |

## Final verification

```json
{
 "answer": "",
 "correct": false
}
```

**Score justification:** PORT.txt='' [TIMEOUT] | t1=240.1s exit=-9 reqs=4 429=0 tools~0; t2=150.0s exit=-9

## Artifacts

- `trace.jsonl` — full CLI stdout/stderr stream with timestamps
- `proxy.jsonl` — wire-level request/response log (secrets redacted)
- `diff.patch` — cumulative git diff of the agent's repository changes
- `result.json` — machine-readable metrics + verification