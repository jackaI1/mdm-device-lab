"""Build the enrollment and last check-in report for every device the server knows about."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

STALE_AFTER = timedelta(hours=24)
FIELDS = ["device_id", "name", "enrollment_status", "last_check_in", "check_in_status"]


def _parse_time(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        # Servers commonly store times as milliseconds since 1970.
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def build_report(devices: list[dict[str, Any]], now: datetime | None = None,
                 stale_after: timedelta = STALE_AFTER) -> list[dict[str, str]]:
    now = now or datetime.now(UTC)
    rows = []
    for device in devices:
        last = _parse_time(device.get("lastUpdate") or device.get("lastCheckIn"))
        if last is None:
            check_in = "never"
        elif now - last > stale_after:
            check_in = "stale"
        else:
            check_in = "ok"
        enrolled = device.get("enrolled", True)
        rows.append({
            "device_id": str(device.get("id", "")),
            "name": str(device.get("number") or device.get("name") or ""),
            "enrollment_status": "enrolled" if enrolled else "not enrolled",
            "last_check_in": last.isoformat(timespec="seconds") if last else "",
            "check_in_status": check_in,
        })
    return rows


def write_csv(rows: list[dict[str, str]], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def to_markdown(rows: list[dict[str, str]]) -> str:
    lines = ["| " + " | ".join(FIELDS) + " |", "|" + "---|" * len(FIELDS)]
    for row in rows:
        lines.append("| " + " | ".join(row[f] for f in FIELDS) + " |")
    return "\n".join(lines) + "\n"
