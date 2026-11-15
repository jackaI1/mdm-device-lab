"""Command line entry point: python -m mdm_lab <command>.

Connection settings come from environment variables so passwords never sit in a file:
  HMDM_URL, HMDM_LOGIN, HMDM_PASSWORD
Devices are named by their Headwind "number" (the name the device was enrolled with).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from typing import Any

from .client import MdmClient, MdmError
from .groups import GroupsError, load_groups
from .policy import PolicyError, build_configuration, configuration_name, describe
from .report import build_report, to_markdown, write_csv


def _client(args: argparse.Namespace) -> MdmClient:
    url = os.environ.get("HMDM_URL")
    login = os.environ.get("HMDM_LOGIN")
    password = os.environ.get("HMDM_PASSWORD")
    if not (url and login and password):
        raise MdmError("set HMDM_URL, HMDM_LOGIN and HMDM_PASSWORD first")
    return MdmClient(url, login, password)


def _device_by_number(client: MdmClient, number: str) -> dict[str, Any]:
    for device in client.list_devices():
        if str(device.get("number")) == number:
            return device
    raise MdmError(f"no enrolled device with number {number!r} on this server")


def cmd_push(args: argparse.Namespace) -> int:
    groups = load_groups(args.groups_csv)
    if not args.apply:
        print("DRY RUN (add --apply to send). Nothing has been changed.")
        for group in groups:
            print(f"group {group.name}: {len(group.device_numbers)} device(s)")
            for line in describe(group):
                print(f"  {line}")
            for number in group.device_numbers:
                print(f"  would assign {number} to {configuration_name(group)}")
        return 0

    client = _client(args)
    devices = {str(d.get("number")): d for d in client.list_devices()}
    apps = client.list_applications()
    failures = 0
    for group in groups:
        print(f"group {group.name}: {len(group.device_numbers)} device(s)")
        ids: list[int] = []
        for number in group.device_numbers:
            if number not in devices:
                print(f"  skip {number}: not enrolled on this server")
                failures += 1
            else:
                ids.append(int(devices[number]["id"]))
        if not ids:
            continue
        try:
            current = client.find_configuration(configuration_name(group))
            saved = client.save_configuration(build_configuration(group, current, apps))
            client.assign_devices(ids, int(saved["id"]))
        except (MdmError, PolicyError) as exc:
            print(f"  FAILED group {group.name}: {exc}")
            failures += 1
            continue
        print(f"  assigned {len(ids)} device(s) to configuration {saved['id']} ({configuration_name(group)})")
    return 1 if failures else 0


def cmd_command(args: argparse.Namespace) -> int:
    if args.command == "wipe" and not args.yes:
        print("wipe erases the whole device. Re-run with --yes to confirm.", file=sys.stderr)
        return 2
    client = _client(args)
    device = _device_by_number(client, args.device_number)
    client.send_command(int(device["id"]), args.command)
    print(f"{args.command} sent to {args.device_number}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    rows = build_report(_client(args).list_devices(), now=datetime.now(UTC))
    write_csv(rows, args.out)
    print(to_markdown(rows))
    print(f"wrote {len(rows)} row(s) to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdm_lab", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command_name", required=True)

    push = sub.add_parser("push", help="send each group's settings to its devices")
    push.add_argument("groups_csv")
    push.add_argument("--apply", action="store_true", help="actually send (default is a dry run)")
    push.set_defaults(func=cmd_push)

    for name in ("lock", "wipe"):
        p = sub.add_parser(name, help=f"{name} one device remotely")
        p.add_argument("device_number")
        if name == "wipe":
            p.add_argument("--yes", action="store_true", help="required to confirm a wipe")
        p.set_defaults(func=cmd_command, command=name)

    report = sub.add_parser("report", help="write enrollment and check-in report")
    report.add_argument("--out", default="device-report.csv")
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except GroupsError as exc:
        print("CSV problems:\n" + str(exc), file=sys.stderr)
        return 2
    except (MdmError, PolicyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
