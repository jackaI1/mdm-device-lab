"""A small in-process stand-in for a Headwind server, so the unit tests need no Docker or emulator.

The response shapes copy what Headwind's open-source server returns: login gives a bare
{"id_token": ...}; most other endpoints wrap their answer as {"status": "OK", "data": ...}.
The live check in CI (.github/workflows/live.yml) runs the same CLI against a real Headwind.
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from mdm_lab import client as api

TOKEN = "test-token"
MD5_SECRET = hashlib.md5(b"secret").hexdigest()


def _initial_devices() -> list[dict]:
    return [
        {"id": 1, "number": "pixel-01", "enrollTime": 1_700_000_000_000, "lastUpdate": None,
         "configurationId": None},
        {"id": 2, "number": "pixel-02", "enrollTime": 1_700_000_000_000, "lastUpdate": None,
         "configurationId": None},
    ]


class FakeHeadwind:
    def __init__(self, plugin_enabled: bool = False):
        self.plugin_enabled = plugin_enabled
        self.requests: list[tuple[str, str, object]] = []
        self.devices = _initial_devices()
        self.apps = [{"id": 10, "pkg": "com.example.notes"}, {"id": 11, "pkg": "com.example.mail"}]
        self.configurations: dict[int, dict] = {}
        self.fail_paths: set[str] = set()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    # --- helpers that mirror the server's behaviour -------------------------------------
    def _wrap(self, data):
        return {"status": "OK", "message": None, "data": data}

    def _save_configuration(self, body: dict) -> dict:
        config = dict(body)
        if config.get("id") is None:
            config["id"] = max(self.configurations, default=100) + 1
        self.configurations[config["id"]] = config
        return config

    def _assign(self, body: dict) -> None:
        for device in self.devices:
            if device["id"] in body["ids"]:
                device["configurationId"] = body["configurationId"]

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
                path = urlsplit(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                fake.requests.append((method, path, body))
                if path in fake.fail_paths:
                    return self._reply(500, {"error": "boom"})
                if path == api.LOGIN_PATH:
                    if body == {"login": "admin", "password": MD5_SECRET}:
                        return self._reply(200, {"id_token": TOKEN})
                    return self._reply(401, {"error": "bad login"})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._reply(401, {"error": "no token"})
                if method == "POST" and path == api.DEVICES_SEARCH_PATH:
                    page = body.get("pageNum", 1)
                    size = body.get("pageSize", 50)
                    items = fake.devices[(page - 1) * size: page * size]
                    return self._reply(200, fake._wrap({"items": items,
                                                        "totalItemsCount": len(fake.devices)}))
                if method == "GET" and path == api.APPLICATIONS_SEARCH_PATH:
                    return self._reply(200, fake._wrap(fake.apps))
                if method == "GET" and path == api.CONFIGURATIONS_SEARCH_PATH:
                    summary = [{"id": c["id"], "name": c["name"]} for c in fake.configurations.values()]
                    return self._reply(200, fake._wrap(summary))
                if method == "GET" and path.startswith(api.CONFIGURATIONS_PATH + "/"):
                    config_id = int(path.rsplit("/", 1)[1])
                    return self._reply(200, fake._wrap(fake.configurations.get(config_id)))
                if method == "PUT" and path == api.CONFIGURATIONS_PATH:
                    return self._reply(200, fake._wrap(fake._save_configuration(body)))
                if method == "PUT" and path == api.DEVICES_PATH:
                    fake._assign(body)
                    return self._reply(200, fake._wrap(None))
                if method == "PUT" and path in api.COMMAND_PATHS.values():
                    if not fake.plugin_enabled:
                        return self._reply(404, {"error": "not found"})
                    return self._reply(200, fake._wrap(None))
                return self._reply(404, {"error": "unknown route"})

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_PUT(self):
                self._handle("PUT")

        return Handler

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
