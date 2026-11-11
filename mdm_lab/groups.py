"""Read the device-group spreadsheet (a CSV file) and check every row before anything is pushed."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = ["group", "device_ids"]
OPTIONAL_COLUMNS = ["wifi_ssid", "wifi_password", "wifi_security",
                    "apps", "min_password_length", "require_password"]
WIFI_SECURITY = {"NONE", "WPA2", "WPA3"}


class GroupsError(ValueError):
    """Raised with a list of every problem found in the CSV, each with its line number."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass
class DeviceGroup:
    name: str
    device_ids: list[str]
    line: int
    wifi_ssid: str = ""
    wifi_password: str = ""
    wifi_security: str = "WPA2"
    apps: list[str] = field(default_factory=list)
    min_password_length: int | None = None
    require_password: bool = False


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def load_groups(path: str | Path) -> list[DeviceGroup]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        problems = [f"missing column: {c}" for c in REQUIRED_COLUMNS if c not in headers]
        if problems:
            raise GroupsError(problems)

        groups: list[DeviceGroup] = []
        seen_names: set[str] = set()
        for row in reader:
            line = reader.line_num
            row = {k: (v or "").strip() for k, v in row.items() if k}
            name = row.get("group", "")
            ids = _split(row.get("device_ids", ""))
            if not name:
                problems.append(f"line {line}: group name is empty")
            elif name in seen_names:
                problems.append(f"line {line}: group {name!r} appears twice")
            seen_names.add(name)
            if not ids:
                problems.append(f"line {line}: group {name!r} has no device_ids")

            security = (row.get("wifi_security") or "WPA2").upper()
            if security not in WIFI_SECURITY:
                problems.append(f"line {line}: wifi_security must be one of {sorted(WIFI_SECURITY)}")

            min_len: int | None = None
            raw_min = row.get("min_password_length", "")
            if raw_min:
                if raw_min.isdigit() and 1 <= int(raw_min) <= 16:
                    min_len = int(raw_min)
                else:
                    problems.append(f"line {line}: min_password_length must be 1-16")

            require = (row.get("require_password") or "no").lower()
            if require not in {"yes", "no"}:
                problems.append(f"line {line}: require_password must be yes or no")

            if row.get("wifi_ssid") and not row.get("wifi_password") and security != "NONE":
                problems.append(f"line {line}: wifi_ssid needs a wifi_password (or wifi_security NONE)")

            groups.append(DeviceGroup(
                name=name,
                device_ids=ids,
                line=line,
                wifi_ssid=row.get("wifi_ssid", ""),
                wifi_password=row.get("wifi_password", ""),
                wifi_security=security,
                apps=_split(row.get("apps", "")),
                min_password_length=min_len,
                require_password=require == "yes",
            ))

    if problems:
        raise GroupsError(problems)
    return groups
