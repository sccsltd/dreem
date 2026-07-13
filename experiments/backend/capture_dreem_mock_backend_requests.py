#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import os
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def local_jwt():
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(
        json.dumps(
            {
                "iss": "dreem-local-capture",
                "permissions": "headband=device;dataupload=device;datasample=device;nightreport=device",
            }
        ).encode("utf-8")
    )
    return f"{header}.{payload}."


def safe_name(method, path):
    parsed = urlparse(path)
    value = parsed.path.strip("/").replace("/", "_") or "root"
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return f"{method}_{value}"


class Handler(BaseHTTPRequestHandler):
    server_version = "DreemLocalCapture/0.2"

    def capture(self):
        length = int(self.headers.get("content-length") or "0")
        body = self.rfile.read(length) if length else b""
        stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S.%fZ")
        base = os.path.join(self.server.out_dir, f"{stamp}_{safe_name(self.command, self.path)}")
        headers = {k: v for k, v in self.headers.items()}
        with open(base + ".headers.json", "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "client": self.client_address[0],
                    "method": self.command,
                    "path": self.path,
                    "headers": headers,
                    "body_length": len(body),
                },
                fh,
                indent=2,
                sort_keys=True,
            )
        if body:
            with open(base + ".body", "wb") as fh:
                fh.write(body)
        print(f"{stamp} {self.client_address[0]} {self.command} {self.path} len={len(body)}", flush=True)
        return body

    def send_json(self, status, payload):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def route(self):
        self.capture()
        path = urlparse(self.path).path.rstrip("/")
        if path.endswith("/token") or path == "/token":
            self.send_json(201, {"token": self.server.jwt, "user_id": self.server.user_id})
            return
        if "reportv2" in path or path.endswith("/report"):
            self.send_json(201, {"id": self.server.report_id, "url": None, "message": "OK"})
            return
        if "dataupload" in path or "datasample" in path or "record" in path:
            self.send_json(200, {"id": self.server.report_id, "message": "OK"})
            return
        self.send_json(200, {"message": "OK"})

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_PUT(self):
        self.route()

    def do_PATCH(self):
        self.route()

    def do_DELETE(self):
        self.route()

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--out", required=True)
    parser.add_argument("--user-id", default="11111111-1111-4111-8111-111111111111")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args()

    os.makedirs(args.out, mode=0o700, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.out_dir = args.out
    server.user_id = args.user_id
    server.report_id = "00000000-0000-4000-8000-000000000002"
    server.jwt = local_jwt()
    scheme = "http"
    if args.tls_cert or args.tls_key:
        if not args.tls_cert or not args.tls_key:
            raise SystemExit("--tls-cert and --tls-key must be provided together")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.tls_cert, args.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    print(f"listening {scheme}://{args.host}:{args.port} out={args.out}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
