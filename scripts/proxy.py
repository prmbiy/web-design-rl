#!/usr/bin/env python3
"""
Multithreaded reverse proxy for api.anthropic.com.

Uses only stdlib. Each request runs in its own thread.

Usage:
    python scripts/proxy.py            # default port 9000
    python scripts/proxy.py --port 9001
"""

import argparse
import ssl
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "https://api.anthropic.com"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


class ProxyHandler(BaseHTTPRequestHandler):
    def do_request(self):
        body = None
        length = int(self.headers.get("Content-Length", 0))
        if length:
            body = self.rfile.read(length)

        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "transfer-encoding", "content-length")
        }

        url = f"{UPSTREAM}{self.path}"
        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, context=_ssl_ctx, timeout=300) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding",):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding",):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

    def do_GET(self):    self.do_request()
    def do_POST(self):   self.do_request()
    def do_PUT(self):    self.do_request()
    def do_DELETE(self): self.do_request()
    def do_PATCH(self):  self.do_request()

    def log_message(self, fmt, *args):
        print(f"[proxy] {self.address_string()} {fmt % args}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"[proxy] Listening on {args.host}:{args.port} → {UPSTREAM} (threaded)")
    server.serve_forever()


if __name__ == "__main__":
    main()
