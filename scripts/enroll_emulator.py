"""Enroll a running Android emulator with the Headwind launcher, using only adb and taps.

Run this on a machine where an emulator is booted and `adb` is on the PATH (the live CI
workflow does this). It installs the Headwind launcher, makes it the device owner, then
types the server URL and the device number into the launcher's own dialogs.

Usage: python scripts/enroll_emulator.py --apk hmdm.apk --server http://10.0.2.2:8080 --number pixel-01
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PACKAGE = "com.hmdm.launcher"
ADMIN_RECEIVER = f"{PACKAGE}/.AdminReceiver"
CONTINUE_LABELS = {"OK", "Ok", "Next", "Continue", "Allow", "Accept", "Got it", "Done", "Start", "Finish"}
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def adb(*args: str, check: bool = True) -> str:
    result = subprocess.run(["adb", *args], check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"adb {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout


def screen_nodes() -> list[ET.Element]:
    adb("shell", "uiautomator", "dump", "/sdcard/hmdm-window.xml", check=False)
    xml_text = adb("exec-out", "cat", "/sdcard/hmdm-window.xml", check=False)
    try:
        return list(ET.fromstring(xml_text).iter("node"))
    except ET.ParseError:
        return []


def center(node: ET.Element) -> tuple[int, int] | None:
    match = BOUNDS.fullmatch(node.get("bounds", ""))
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def tap(node: ET.Element) -> None:
    point = center(node)
    if point:
        adb("shell", "input", "tap", str(point[0]), str(point[1]))


def type_text(node: ET.Element, text: str) -> None:
    tap(node)
    time.sleep(0.5)
    adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
    adb("shell", "input", "keyevent", *["KEYCODE_DEL"] * 40)
    adb("shell", "input", "text", text.replace(" ", "%s"))


def find(nodes: list[ET.Element], id_suffix: str) -> ET.Element | None:
    return next((n for n in nodes if n.get("resource-id", "").endswith(id_suffix)), None)


def step(nodes: list[ET.Element], attempts: dict[str, int]) -> bool:
    """Do one thing on the current screen. Return False when nothing matched."""
    server_field = find(nodes, "id/server_url")
    if server_field is not None and attempts.get("server", 0) < 3:
        attempts["server"] = attempts.get("server", 0) + 1
        type_text(server_field, SERVER)
        save = find(nodes, "id/saveServerUrl")
        if save is not None:
            tap(save)
        print(f"entered server URL (attempt {attempts['server']})")
        return True
    device_field = find(nodes, "id/device_id")
    if device_field is not None and attempts.get("device", 0) < 3:
        attempts["device"] = attempts.get("device", 0) + 1
        type_text(device_field, NUMBER)
        save = find(nodes, "id/saveDeviceId")
        if save is not None:
            tap(save)
        print(f"entered device number {NUMBER} (attempt {attempts['device']})")
        return True
    for node in nodes:
        if node.get("clickable") == "true" and node.get("text") in CONTINUE_LABELS:
            print(f"tapping {node.get('text')!r}")
            tap(node)
            return True
    return False


def describe_screen(nodes: list[ET.Element]) -> str:
    ids = sorted({n.get("resource-id", "") for n in nodes if n.get("resource-id")})
    texts = sorted({n.get("text", "") for n in nodes if n.get("text")})
    return f"resource-ids: {ids[:25]}\ntexts: {texts[:25]}"


def main() -> int:
    global SERVER, NUMBER
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--number", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    SERVER, NUMBER = args.server, args.number

    adb("install", "-r", args.apk)
    print(adb("shell", "dpm", "set-device-owner", ADMIN_RECEIVER, check=False).strip())
    adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1", check=False)

    attempts: dict[str, int] = {}
    deadline = time.time() + args.timeout
    quiet_rounds = 0
    nodes: list[ET.Element] = []
    while time.time() < deadline:
        time.sleep(3)
        nodes = screen_nodes()
        if step(nodes, attempts):
            quiet_rounds = 0
            continue
        quiet_rounds += 1
        if quiet_rounds >= 5:
            # Nothing left to click for a while: the launcher is probably running.
            print("no more setup dialogs; leaving the launcher to check in")
            return 0
    print("timed out waiting for the launcher setup dialogs", file=sys.stderr)
    print(describe_screen(nodes), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
