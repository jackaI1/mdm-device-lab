"""Command line entry point: python -m mdm_lab <command>.

Connection settings come from environment variables so passwords never sit in a file:
  HMDM_URL, HMDM_LOGIN, HMDM_PASSWORD
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

from .client import MdmClient, MdmError
from .groups import GroupsError, load_groups
from .policy import build_policy
from .report import build_report, to_markdown, write_csv


def _client(args: argparse.Namespace) -> MdmClient:
    url = os.environ.get("HMDM_URL")
    login = os.environ.get("HMDM_LOGIN")
    password = os.environ.get("HMDM_PASSWORD")
    if not (url and login and password):
        raise MdmError("set HMDM_URL, HMDM_LOGIN and HMDM_PASSWORD first")
    return MdmClient(url, login, password)


def cmd_push(args: argparse.Namespace) -> int:
    groups = load_groups(args.groups_csv)
    if not args.apply:
        print("DRY RUN (add --apply to send). Nothing has been changed.")
    client = _client(args) if args.apply else None
    known = {str(d.get("id")) for d in client.list_devices()} if client else None
    failures = 0
    for group in groups:
        policy = build_policy(group)
        print(f"group {group.name}: {len(group.device_ids)} device(s), policy keys {sorted(policy)}")
        for device_id in group.device_ids:
            if args.apply:
                if device_id not in known:
                    print(f"  skip {device_id}: not enrolled on this server")
                    failures += 1
                    continue
                try:
                    client.apply_policy(device_id, policy)
                    print(f"  sent to {device_id}")
                except MdmError as exc:
                    print(f"  FAILED {device_id}: {exc}")
                    failures += 1
            else:
                print(f"  would send to {device_id}")
    return 1 if failures else 0


def cmd_command(args: argparse.Namespace) -> int:
    if args.command == "wipe" and not args.yes:
        print("wipe erases the whole device. Re-run with --yes to confirm.", file=sys.stderr)
        return 2
    _client(args).send_command(args.device_id, args.command)
    print(f"{args.command} sent to {args.device_id}")
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

    push = sub.add_parser("push", help="send each group's policy to its devices")
    push.add_argument("groups_csv")
    push.add_argument("--apply", action="store_true", help="actually send (default is a dry run)")
    push.set_defaults(func=cmd_push)

    for name in ("lock", "wipe"):
        p = sub.add_parser(name, help=f"{name} one device remotely")
        p.add_argument("device_id")
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
    except MdmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
