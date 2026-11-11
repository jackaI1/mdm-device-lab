"""A small HTTP client for a Headwind MDM server (an open-source MDM, not Microsoft Intune).

The server is reached over its REST API using only the Python standard library.

The endpoint paths below are my best reading of Headwind's REST layout. They are
kept in one place so they are easy to change. Check them against the API of the
server version you run before trusting a real device to them.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

LOGIN_PATH = "/rest/public/jwt/login"
DEVICES_SEARCH_PATH = "/rest/private/devices/search"
POLICY_PATH = "/rest/private/devices/{device_id}/configuration"
COMMAND_PATH = "/rest/private/devices/{device_id}/command"

ALLOWED_COMMANDS = {"lock", "wipe"}
PAGE_SIZE = 200


class MdmError(Exception):
    """Raised when the MDM server cannot be reached or refuses a request."""


class MdmClient:
    def __init__(self, base_url: str, login: str, password: str,
                 timeout: float = 15.0, opener: urllib.request.OpenerDirector | None = None):
        self.base_url = base_url.rstrip("/")
        self._login = login
        self._password = password
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener()
        self._token: str | None = None

    def authenticate(self) -> None:
        data = self._call("POST", LOGIN_PATH,
                          {"login": self._login, "password": self._password}, auth=False)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise MdmError("login succeeded but the server returned no token")
        self._token = token

    def list_devices(self) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._call("POST", DEVICES_SEARCH_PATH, {"page": page, "pageSize": PAGE_SIZE})
            items = data.get("data", []) if isinstance(data, dict) else list(data or [])
            devices.extend(items)
            if len(items) < PAGE_SIZE:
                return devices
            page += 1

    def apply_policy(self, device_id: str, policy: dict[str, Any]) -> None:
        self._call("POST", POLICY_PATH.format(device_id=device_id), policy)

    def send_command(self, device_id: str, command: str) -> None:
        if command not in ALLOWED_COMMANDS:
            raise MdmError(f"unknown command {command!r}; allowed: {sorted(ALLOWED_COMMANDS)}")
        self._call("POST", COMMAND_PATH.format(device_id=device_id), {"command": command})

    def _call(self, method: str, path: str, body: Any = None, auth: bool = True) -> Any:
        if auth and self._token is None:
            self.authenticate()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=payload,
                                        headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise MdmError(f"{method} {path} failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise MdmError(f"could not reach {self.base_url}: {exc.reason}") from exc
        return json.loads(raw) if raw else {}
