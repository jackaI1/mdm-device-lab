"""Turn one device group into the Headwind configuration that its devices will receive.

In Headwind a "configuration" is the bundle of settings a device runs with (Wi-Fi,
the apps it installs, its password rule). Each group gets one configuration, and
its devices are assigned to it. A group only changes the settings it fills in;
blank CSV cells leave the existing value alone.
"""

from __future__ import annotations

from typing import Any

from .groups import DeviceGroup

CONFIGURATION_PREFIX = "mdm-lab "
APP_ACTION_INSTALL = 1  # Headwind's application link action: install on the device


class PolicyError(ValueError):
    """Raised when a group refers to something the server does not have."""


def configuration_name(group: DeviceGroup) -> str:
    return f"{CONFIGURATION_PREFIX}{group.name}"


def build_configuration(group: DeviceGroup, current: dict[str, Any] | None,
                        app_ids: dict[str, int]) -> dict[str, Any]:
    """Return the full configuration to save. `current` is the server's copy, if it exists.

    Headwind saves a configuration as a whole, so we start from the server's copy and
    change only the fields this group sets. That keeps settings the CSV does not mention.
    """
    missing = [pkg for pkg in group.apps if pkg not in app_ids]
    if missing:
        raise PolicyError(f"group {group.name!r}: these apps are not uploaded to the server: "
                          + ", ".join(missing))

    config: dict[str, Any] = dict(current) if current else {
        "name": configuration_name(group),
        "type": 0,
        "description": "Managed by mdm-device-lab from the groups CSV",
    }
    if group.wifi_ssid:
        config["wifiSSID"] = group.wifi_ssid
        config["wifiPassword"] = group.wifi_password
        config["wifiSecurityType"] = group.wifi_security
    if group.password_mode:
        config["passwordMode"] = group.password_mode
    if group.apps:
        config["applications"] = [{"id": app_ids[pkg], "action": APP_ACTION_INSTALL} for pkg in group.apps]
    return config


def describe(group: DeviceGroup) -> list[str]:
    """The settings a group will change, for the dry-run output."""
    lines = []
    if group.wifi_ssid:
        lines.append(f"wifi {group.wifi_ssid} ({group.wifi_security})")
    if group.apps:
        lines.append("apps " + ", ".join(group.apps))
    if group.password_mode:
        lines.append(f"password mode {group.password_mode}")
    return lines or ["no settings (devices are only assigned)"]
