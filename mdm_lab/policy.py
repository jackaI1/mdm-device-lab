"""Turn one device group into the policy payload that gets sent to each device."""

from __future__ import annotations

from typing import Any

from .groups import DeviceGroup


def build_policy(group: DeviceGroup) -> dict[str, Any]:
    policy: dict[str, Any] = {"group": group.name}
    if group.wifi_ssid:
        policy["wifi"] = {
            "ssid": group.wifi_ssid,
            "password": group.wifi_password,
            "security": group.wifi_security,
        }
    if group.apps:
        policy["apps"] = [{"package": pkg, "action": "install"} for pkg in group.apps]
    password: dict[str, Any] = {"required": group.require_password}
    if group.min_password_length is not None:
        password["minLength"] = group.min_password_length
    if group.require_password or group.min_password_length is not None:
        policy["password"] = password
    return policy
