"""Canonical comparison transport. Reads never create or migrate a workspace."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from rks.config import load_paths
from rks.operations.comparison import apply_comparison, list_comparisons, list_evidence, show_comparison
from rks.storage.db import connect_db_readonly


def register(subparsers):
    parser = subparsers.add_parser("comparison", help="Compare selected imported evidence and record scoped human reviews.")
    commands = parser.add_subparsers(dest="comparison_command", required=True)
    for name in ("list", "show", "apply", "evidence"):
        command = commands.add_parser(name)
        command.add_argument("--workspace-id", required=True)
        command.add_argument("--source-id", required=True)
        command.add_argument("--paper-source", action="append", required=True)
        if name == "show":
            command.add_argument("comparison_id")
            command.add_argument("--history", action="store_true")
        if name == "apply":
            command.add_argument("request", type=Path, help="Saved versioned comparison request JSON.")
        command.set_defaults(handler=handle)


def handle(args):
    scope = {"workspace_id": args.workspace_id, "source_id": args.source_id, "paper_sources": args.paper_source}
    path = load_paths().db_path
    if args.comparison_command == "apply":
        request = json.loads(args.request.read_text(encoding="utf-8-sig"))
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=rw", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            result = apply_comparison(conn, request, **scope)
    else:
        with closing(connect_db_readonly(path)) as conn:
            conn.execute("BEGIN")
            if args.comparison_command == "list":
                result = list_comparisons(conn, **scope)
            elif args.comparison_command == "evidence":
                result = list_evidence(conn, **scope)
            else:
                result = show_comparison(conn, args.comparison_id, history=args.history, **scope)
    print(json.dumps(result, indent=2))
    return 0
