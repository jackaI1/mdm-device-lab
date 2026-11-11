"""A tiny in-process stand-in for the MDM server, so tests run without Docker or emulators."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mdm_lab import client as api

TOKEN = "test-token"
DEVICES = [
    {"id": "1", "number": "pixel-01", "enrolled": True, "lastUpdate": None},
    {"id": "2", "number": "pixel-02", "enrolled": True, "lastUpdate": None},
]


class FakeMdm:
    def __init__(self):
        self.requests: list[tuple[str, str, dict | None]] = []
        self.devices = list(DEVICES)
        self.fail_paths: set[str] = set()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _reply(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                fake.requests.append((method, self.path, body))
                if self.path in fake.fail_paths:
                    return self._reply(500, {"error": "boom"})
                if self.path == api.LOGIN_PATH:
                    if body == {"login": "admin", "password": "secret"}:
                        return self._reply(200, {"token": TOKEN})
                    return self._reply(401, {"error": "bad login"})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._reply(401, {"error": "no token"})
                if self.path == api.DEVICES_SEARCH_PATH:
                    return self._reply(200, {"data": fake.devices})
                if self.path.endswith("/configuration") or self.path.endswith("/command"):
                    device_id = self.path.split("/")[4]
                    if device_id not in {d["id"] for d in fake.devices}:
                        return self._reply(404, {"error": "no such device"})
                    return self._reply(200, {"ok": True})
                return self._reply(404, {"error": "unknown route"})

            def do_POST(self):
                self._handle("POST")

        return Handler

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
