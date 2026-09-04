#!/usr/bin/env python3
"""
Pacing reverse proxy for NVIDIA NIM (hermes integration shim).

Forwards to https://integrate.api.nvidia.com, injects the API key (hermes
strips auth for loopback base URLs), and enforces a minimum spacing between
/v1/chat/completions POSTs — the client-side equivalent of SHS Code's
rate_limit rpm setting, so every CLI gets comparable access to the same
NIM token-bucket quota. Run standalone or import start_proxy().
"""
import http.server, urllib.request, json, threading, time

LOG = "/tmp/proxy.log"
UP = "https://integrate.api.nvidia.com"
PORT = 8899
MIN_GAP = 11.0  # seconds between chat-completions POSTs (~5-6 req/min)

NIM_KEY = [l.split("=", 1)[1].strip().strip('"')
           for l in open("/home/z/my-project/.secrets/nim.env")
           if l.startswith("export NVIDIA_API_KEY=")][0]

_lock = threading.Lock()
_last_chat = [0.0]


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _relay(self):
        body = b""
        cl = self.headers.get("Content-Length")
        if cl:
            body = self.rfile.read(int(cl))
        model = stream_flag = ""
        try:
            if body:
                j = json.loads(body)
                model = j.get("model", "")
                stream_flag = f" stream={j.get('stream')}"
        except Exception:
            pass

        is_chat = self.command == "POST" and "/chat/completions" in self.path
        if is_chat:
            with _lock:
                wait = MIN_GAP - (time.time() - _last_chat[0])
                if wait > 0:
                    time.sleep(wait)
                _last_chat[0] = time.time()

        req = urllib.request.Request(UP + self.path, data=body if body else None,
                                     method=self.command)
        for h in ("Content-Type", "Accept", "User-Agent"):
            v = self.headers.get(h)
            if v:
                req.add_header(h, v)
        req.add_header("Authorization", f"Bearer {NIM_KEY}")

        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = r.read()
                code = r.status
        except urllib.error.HTTPError as e:
            data = e.read()
            code = e.code
        except Exception as e:
            data, code = str(e).encode(), 502

        with open(LOG, "a") as f:
            f.write(f"{self.command} {self.path} {model}{stream_flag} -> {code} ({len(data)}b)\n")

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    do_GET = do_POST = _relay

    def log_message(self, *a):
        pass


def start_proxy(port=PORT):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


if __name__ == "__main__":
    print(f"pacing proxy on 127.0.0.1:{PORT} -> {UP} (gap {MIN_GAP}s)")
    start_proxy()
    while True:
        time.sleep(3600)
