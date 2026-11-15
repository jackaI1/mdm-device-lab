"""Build the enrollment and last check-in report for every device the server knows about."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

STALE_AFTER = timedelta(hours=24)
FIELDS = ["device_number", "enrollment_status", "enrolled_at", "last_check_in", "check_in_status"]


def _from_millis(value: Any) -> datetime | None:
    """Headwind stores times as milliseconds since 1970. Zero or empty means "never"."""
    if value in (None, "", 0, "0"):
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def build_report(devices: list[dict[str, Any]], now: datetime | None = None,
                 stale_after: timedelta = STALE_AFTER) -> list[dict[str, str]]:
    now = now or datetime.now(UTC)
    rows = []
    for device in devices:
        enrolled_at = _from_millis(device.get("enrollTime"))
        last = _from_millis(device.get("lastUpdate"))
        if last is None:
            check_in = "never"
        elif now - last > stale_after:
            check_in = "stale"
        else:
            check_in = "ok"
        rows.append({
            "device_number": str(device.get("number") or ""),
            "enrollment_status": "enrolled" if enrolled_at else "not enrolled",
            "enrolled_at": enrolled_at.isoformat(timespec="seconds") if enrolled_at else "",
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
