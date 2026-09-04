#!/usr/bin/env python3
"""Forensic benchmark proxy — logs every request; optional fault injection.

Modes (via --mode):
  passthrough : forward + log only
  fault502    : first N requests -> HTTP 502, then passthrough (N via --n)
  rate429     : first N OK, next M requests -> 429 + Retry-After, then passthrough
  slow429     : every 3rd request -> 429 with Retry-After: 20

All requests/responses logged to JSONL (redacted) for trace capture.
Supports streaming (SSE) relay for chat completions.
"""
import argparse
import asyncio
import json
import time
import sys
from pathlib import Path

import aiohttp
from aiohttp import web

UPSTREAM = "https://integrate.api.nvidia.com/v1"
SECRET_PATTERNS = ["nvapi-", "ghp_", "hf_"]


def redact(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        idx = 0
        while True:
            i = out.find(pat, idx)
            if i == -1:
                break
            # redact until next quote/space/bracket
            j = i
            while j < len(out) and out[j] not in '"\' \n<,)]}':
                j += 1
            out = out[:i] + pat + "…[REDACTED]"
            idx = i + len(pat) + 11
    return out


class ProxyState:
    def __init__(self, mode: str, n: int, m: int, log_path: Path, pace: float = 0):
        self.mode = mode
        self.n = n
        self.m = m
        self.pace = pace
        self.count = 0
        self.log_path = log_path
        self.log_fh = open(log_path, "a")
        self.log_lock = asyncio.Lock()   # logging only — never held during sleeps
        self.pace_lock = asyncio.Lock()  # pacing only
        self.last_forward = 0.0
        self.paced_delays = 0

    async def log(self, event: dict):
        async with self.log_lock:
            self.log_fh.write(json.dumps(event, default=str) + "\n")
            self.log_fh.flush()

    def decide(self) -> str:
        """Return action for this request: ok | 502 | 429."""
        self.count += 1
        c = self.count
        if self.mode == "fault502" and c <= self.n:
            return "502"
        if self.mode == "rate429":
            if c <= self.n:
                return "ok"
            if c <= self.n + self.m:
                return "429"
            return "ok"
        if self.mode == "slow429" and c % 3 == 0:
            return "429"
        return "ok"


async def handle(request: web.Request, state: ProxyState) -> web.StreamResponse:
    t0 = time.time()
    body = await request.read()
    body_str = redact(body.decode("utf-8", errors="replace"))[:4000] if body else ""
    req_id = f"req{state.count + 1}"
    action = state.decide()

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "authorization", "content-length")}
    auth = request.headers.get("Authorization", "")
    auth_red = redact(auth)

    await state.log({
        "ts": t0, "id": req_id, "event": "request", "action": action,
        "method": request.method, "path": request.path,
        "auth": auth_red[:20] + "…" if auth else None,
        "body": body_str,
    })

    if action == "502":
        await state.log({"ts": time.time(), "id": req_id, "event": "injected_502"})
        return web.Response(status=502, text="injected fault: bad gateway (bench proxy)")

    if action == "429":
        await state.log({"ts": time.time(), "id": req_id, "event": "injected_429"})
        return web.Response(
            status=429, content_type="application/problem+json",
            headers={"Retry-After": "20"},
            text='{"status":429,"title":"Too Many Requests"}')

    # fair-share pacing: hold CHAT-COMPLETION requests until `pace` seconds
    # after the previous forwarded chat request (capacity division across
    # parallel agents). Discovery probes (404s, models lists) pass unpaced.
    is_chat = request.path.endswith("/chat/completions")
    if state.pace > 0 and is_chat:
        async with state.pace_lock:
            now = time.time()
            wait = state.last_forward + state.pace - now
            if wait > 0:
                state.paced_delays += 1
                await state.log({"ts": now, "id": req_id, "event": "paced_wait",
                                 "wait_s": round(wait, 1)})
                await asyncio.sleep(wait)
            state.last_forward = time.time()

    # passthrough with streaming relay
    url = UPSTREAM + request.path
    send_headers = {k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "content-length", "transfer-encoding")}
    session: aiohttp.ClientSession = request.app["session"]
    try:
        async with session.request(request.method, url, data=body,
                                   headers=send_headers,
                                   timeout=aiohttp.ClientTimeout(total=600)) as up:
            resp = web.StreamResponse(status=up.status,
                                      headers={k: v for k, v in up.headers.items()
                                               if k.lower() not in
                                               ("content-length", "transfer-encoding",
                                                "content-encoding", "connection")})
            await resp.prepare(request)
            total_bytes = 0
            done_seen = False
            async for chunk in up.content.iter_any():
                total_bytes += len(chunk)
                await resp.write(chunk)
                # SSE end-of-stream marker: upstream may keep the connection
                # open after [DONE]; stop relaying once the client has it.
                if b"[DONE]" in chunk:
                    done_seen = True
                    break
            try:
                await resp.write_eof()
            except Exception:
                pass
            await state.log({
                "ts": time.time(), "id": req_id, "event": "response",
                "status": up.status, "bytes": total_bytes, "sse_done": done_seen,
                "dur_s": round(time.time() - t0, 2),
            })
            return resp
    except Exception as e:
        await state.log({"ts": time.time(), "id": req_id, "event": "proxy_error",
                         "error": str(e)[:300]})
        return web.Response(status=502, text=f"proxy error: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8321)
    ap.add_argument("--mode", default="passthrough",
                    choices=["passthrough", "fault502", "rate429", "slow429"])
    ap.add_argument("--n", type=int, default=2, help="fault502: N fails; rate429: N ok first")
    ap.add_argument("--m", type=int, default=3, help="rate429: M 429s after first N")
    ap.add_argument("--pace", type=float, default=0,
                    help="min seconds between forwarded requests (0=off)")
    ap.add_argument("--log", default="/tmp/bench_proxy.jsonl")
    args = ap.parse_args()

    state = ProxyState(args.mode, args.n, args.m, Path(args.log), args.pace)

    async def make_app():
        app = web.Application()
        app["session"] = aiohttp.ClientSession()
        app.router.add_route("*", "/{tail:.*}",
                             lambda r: handle(r, state))
        return app

    print(f"[bench_proxy] mode={args.mode} port={args.port} pace={args.pace} "
          f"log={args.log}", flush=True)
    web.run_app(make_app(), host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
