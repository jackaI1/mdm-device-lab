"""A small HTTP client for a Headwind MDM server (an open-source MDM, not Microsoft Intune).

The server is reached over its REST API using only the Python standard library.

The paths and field names below were read from Headwind's open-source server code
(github.com/h-mdm/hmdm-server, the JWTAuthResource, DeviceResource, ConfigurationResource
and ApplicationResource classes) and checked against a running server in CI
(see .github/workflows/live.yml). Two things are not in the open-source server:
remote lock and wipe. Headwind ships those in a separate plugin ("devicereset"), so
the lock and wipe paths below return "not found" on a server without that plugin.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Any

# Login: the password must be sent as its MD5 hash, as Headwind's login expects.
LOGIN_PATH = "/rest/public/jwt/login"
DEVICES_PATH = "/rest/private/devices"
DEVICES_SEARCH_PATH = "/rest/private/devices/search"
CONFIGURATIONS_PATH = "/rest/private/configurations"
CONFIGURATIONS_SEARCH_PATH = "/rest/private/configurations/search"
CONFIGURATION_BY_ID_PATH = "/rest/private/configurations/{config_id}"
APPLICATIONS_SEARCH_PATH = "/rest/private/applications/search"
COMMAND_PATHS = {
    "lock": "/rest/plugins/devicereset/private/lock",
    "wipe": "/rest/plugins/devicereset/private/reset",
}

PAGE_SIZE = 200


class MdmError(Exception):
    """Raised when the MDM server cannot be reached or refuses a request."""


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


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
                          {"login": self._login, "password": md5_hex(self._password)}, auth=False)
        token = data.get("id_token") if isinstance(data, dict) else None
        if not token:
            raise MdmError("login succeeded but the server returned no token")
        self._token = token

    def list_devices(self) -> list[dict[str, Any]]:
        """Every enrolled device (Headwind calls the device's name its 'number')."""
        devices: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._call("POST", DEVICES_SEARCH_PATH, {"pageNum": page, "pageSize": PAGE_SIZE})
            items = data.get("items", []) if isinstance(data, dict) else []
            devices.extend(items)
            if len(items) < PAGE_SIZE:
                return devices
            page += 1

    def list_applications(self) -> dict[str, int]:
        """Map of Android package name to Headwind application ID, for apps already uploaded."""
        apps = self._call("GET", APPLICATIONS_SEARCH_PATH) or []
        return {app["pkg"]: app["id"] for app in apps if app.get("pkg") and app.get("id")}

    def find_configuration(self, name: str) -> dict[str, Any] | None:
        for config in self._call("GET", CONFIGURATIONS_SEARCH_PATH) or []:
            if config.get("name") == name:
                return self._call("GET", CONFIGURATION_BY_ID_PATH.format(config_id=config["id"]))
        return None

    def save_configuration(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """Create a configuration (no id) or update one. Headwind pushes the change to its devices."""
        return self._call("PUT", CONFIGURATIONS_PATH, configuration)

    def assign_devices(self, device_db_ids: list[int], configuration_id: int) -> None:
        self._call("PUT", DEVICES_PATH, {"ids": device_db_ids, "configurationId": configuration_id})

    def send_command(self, device_db_id: int, command: str) -> None:
        if command not in COMMAND_PATHS:
            raise MdmError(f"unknown command {command!r}; allowed: {sorted(COMMAND_PATHS)}")
        try:
            self._call("PUT", COMMAND_PATHS[command], {"id": device_db_id})
        except MdmError as exc:
            if "HTTP 404" in str(exc):
                raise MdmError(f"{command} is not available on this server: Headwind's open-source "
                               "server has no device reset plugin (HTTP 404)") from exc
            raise

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
        if not raw:
            return {}
        decoded = json.loads(raw)
        # Most Headwind endpoints wrap their result as {"status": "OK", "data": ...}.
        if isinstance(decoded, dict) and "status" in decoded and "data" in decoded:
            if decoded["status"] != "OK":
                raise MdmError(f"{method} {path} returned {decoded['status']}: {decoded.get('message')}")
            return decoded["data"]
        return decoded
