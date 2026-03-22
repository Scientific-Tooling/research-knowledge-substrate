from __future__ import annotations

import argparse
import json
import sys

from rks.config import ConfigError
from rks.cli.commands import (
    system,
    ingest,
    batch,
    show,
    papers,
    objects,
    notes,
    project,
    extraction,
    import_cmd,
    export_cmd,
    tasks,
    review,
    evolution,
    query,
    output,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    system.register(subparsers)
    ingest.register(subparsers)
    batch.register(subparsers)
    show.register(subparsers)
    papers.register(subparsers)
    objects.register(subparsers)
    notes.register(subparsers)
    project.register(subparsers)
    extraction.register(subparsers)
    import_cmd.register(subparsers)
    export_cmd.register(subparsers)
    tasks.register(subparsers)
    review.register(subparsers)
    evolution.register(subparsers)
    query.register(subparsers)
    output.register(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except ConfigError as exc:
        print(json.dumps({"error": "config_error", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": "internal_error", "type": type(exc).__name__, "message": str(exc)}, indent=2), file=sys.stderr)
        return 1
