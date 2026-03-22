from __future__ import annotations

import argparse
import json

from rks.operations import describe_claim_schema


def register(subparsers) -> None:
    schema_parser = subparsers.add_parser("schema", help="Describe the data structure of RKS objects.")
    schema_subparsers = schema_parser.add_subparsers(dest="schema_command", required=True)

    schema_claim_parser = schema_subparsers.add_parser("claim", help="Show the data structure of a claim object.")
    schema_claim_parser.set_defaults(handler=handle_schema_claim)


def handle_schema_claim(args: argparse.Namespace) -> int:
    print(json.dumps(describe_claim_schema(), indent=2))
    return 0
