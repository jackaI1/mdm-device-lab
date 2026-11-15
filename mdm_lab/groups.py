"""Read the device-group spreadsheet (a CSV file) and check every row before anything is pushed."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = ["group", "device_numbers"]
OPTIONAL_COLUMNS = ["wifi_ssid", "wifi_password", "wifi_security", "apps", "password_mode"]
WIFI_SECURITY = {"NONE", "WPA2", "WPA3"}
# Headwind's own password quality levels, from its Android launcher's settings.
PASSWORD_MODES = {"", "present", "easy", "moderate", "strong"}


class GroupsError(ValueError):
    """Raised with a list of every problem found in the CSV, each with its line number."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass
class DeviceGroup:
    name: str
    device_numbers: list[str]
    line: int
    wifi_ssid: str = ""
    wifi_password: str = ""
    wifi_security: str = "WPA2"
    apps: list[str] = field(default_factory=list)
    password_mode: str = ""


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
            numbers = _split(row.get("device_numbers", ""))
            if not name:
                problems.append(f"line {line}: group name is empty")
            elif name in seen_names:
                problems.append(f"line {line}: group {name!r} appears twice")
            seen_names.add(name)
            if not numbers:
                problems.append(f"line {line}: group {name!r} has no device_numbers")

            security = (row.get("wifi_security") or "WPA2").upper()
            if security not in WIFI_SECURITY:
                problems.append(f"line {line}: wifi_security must be one of {sorted(WIFI_SECURITY)}")

            mode = (row.get("password_mode") or "").lower()
            if mode not in PASSWORD_MODES:
                problems.append(f"line {line}: password_mode must be blank or one of "
                                f"{sorted(PASSWORD_MODES - {''})}")

            if row.get("wifi_ssid") and not row.get("wifi_password") and security != "NONE":
                problems.append(f"line {line}: wifi_ssid needs a wifi_password (or wifi_security NONE)")

            groups.append(DeviceGroup(
                name=name,
                device_numbers=numbers,
                line=line,
                wifi_ssid=row.get("wifi_ssid", ""),
                wifi_password=row.get("wifi_password", ""),
                wifi_security=security,
                apps=_split(row.get("apps", "")),
                password_mode=mode,
            ))

    if problems:
        raise GroupsError(problems)
    return groups
