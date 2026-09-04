#!/usr/bin/env python3
"""Probe NVIDIA NIM minimax-m3 rate limit pattern: 1 request every 20s for 2 minutes."""
import os, time, json, urllib.request, urllib.error
from datetime import datetime

KEY = None
for line in open("/home/z/my-project/.secrets/nim.env"):
    line = line.strip()
    if line.startswith("export NVIDIA_API_KEY="):
        KEY = line.split("=", 1)[1].strip().strip('"')
assert KEY, "no key"

URL = "https://integrate.api.nvidia.com/v1/chat/completions"
BODY = json.dumps({"model": "minimaxai/minimax-m3",
                   "messages": [{"role": "user", "content": "Reply with just: OK"}],
                   "max_tokens": 10}).encode()

def probe():
    req = urllib.request.Request(URL, data=BODY, headers={
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)[:40]

results = []
schedule = [0, 20, 40, 60, 65, 80, 100, 120]
t0 = time.time()
for offset in schedule:
    wait = offset - (time.time() - t0)
    if wait > 0:
        time.sleep(wait)
    code = probe()
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] t=+{time.time()-t0:.0f}s -> HTTP {code}", flush=True)
    results.append((round(time.time()-t0), code))

print("\nSummary:", results)
