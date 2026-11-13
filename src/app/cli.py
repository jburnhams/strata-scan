"""Command line: `doctor` checks the environment, `hello` prints or records a greeting, `serve` starts the web server."""

import argparse
import json
import sys
from collections.abc import Sequence

from strata_python import cli as shared

from app import __version__, greet, settings


def run_server(host: str, port: int) -> None:
    from app.server import app as server_app

    server_app.main(["--host", host, "--port", str(port)])


def cmd_hello(args: argparse.Namespace) -> int:
    try:
        rec = (
            greet.add_message(args.name, args.greeting)
            if args.save
            else greet.format_greeting(args.name, args.greeting)
        )
    except greet.GreetingError as e:
        sys.exit(str(e))
    if args.json:
        print(json.dumps(rec))
        return 0
    print(rec["message"])
    return 0


def cmd_messages(args: argparse.Namespace) -> int:
    if args.clear:
        res = greet.clear_messages()
        print(json.dumps(res) if args.json else f"cleared {res['cleared']} message(s)")
        return 0
    items = greet.list_messages()
    if args.json:
        print(json.dumps(items, indent=1))
        return 0
    if not items:
        print("  (no messages yet: ./app hello World --save)")
        return 0
    for m in items:
        print(f"  #{m['id']:<4} {m['message']:30} ({m['created']})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app")
    sub = p.add_subparsers(dest="cmd", required=True)
    shared.add_doctor(sub, "app", __version__, ("fastapi", "uvicorn", "pydantic", "strata_python"))
    h = sub.add_parser("hello", help="print a greeting (and optionally record it)")
    h.add_argument("name", nargs="?", default="World")
    h.add_argument("--greeting", help="override the default greeting word")
    h.add_argument("--save", action="store_true", help="record the greeting in the message log")
    h.add_argument("--json", action="store_true")
    h.set_defaults(fn=cmd_hello)
    m = sub.add_parser("messages", help="list or clear recorded greetings")
    m.add_argument("--clear", action="store_true")
    m.add_argument("--json", action="store_true")
    m.set_defaults(fn=cmd_messages)
    shared.add_set(sub, settings.SETTINGS)
    shared.add_serve(sub, run_server, default_port=8360)
    a = p.parse_args(argv)
    return a.fn(a)
