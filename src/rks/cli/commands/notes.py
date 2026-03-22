from __future__ import annotations

import argparse
import json

from rks.cli._context import _open_session, _operations


def register(subparsers) -> None:
    note_parser = subparsers.add_parser("note", help="Add or inspect user and agent notes.")
    note_subparsers = note_parser.add_subparsers(dest="note_command", required=True)

    note_add_parser = note_subparsers.add_parser("add", help="Add a note to a stored object.")
    note_add_subparsers = note_add_parser.add_subparsers(dest="note_target", required=True)
    note_add_paper_parser = note_add_subparsers.add_parser("paper", help="Add a note to a paper.")
    note_add_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    note_add_paper_parser.add_argument("--content", required=True, help="Note text to store.")
    note_add_paper_parser.add_argument("--created-by", default="human:user", help="Note author label.")
    note_add_paper_parser.set_defaults(handler=handle_note_add_paper)
    note_add_project_parser = note_add_subparsers.add_parser("project", help="Add a note to a project.")
    note_add_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    note_add_project_parser.add_argument("--content", required=True, help="Note text to store.")
    note_add_project_parser.add_argument("--created-by", default="human:user", help="Note author label.")
    note_add_project_parser.set_defaults(handler=handle_note_add_project)

    note_list_parser = note_subparsers.add_parser("list", help="List notes for a stored object.")
    note_list_subparsers = note_list_parser.add_subparsers(dest="note_target", required=True)
    note_list_paper_parser = note_list_subparsers.add_parser("paper", help="List notes for a paper.")
    note_list_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    note_list_paper_parser.set_defaults(handler=handle_note_list_paper)
    note_list_project_parser = note_list_subparsers.add_parser("project", help="List notes for a project.")
    note_list_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    note_list_project_parser.set_defaults(handler=handle_note_list_project)


def handle_note_add_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_paper_note(
            args.paper_id,
            content=args.content,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_note_add_project(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_project_note(
            args.project_id,
            content=args.content,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_note_list_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_paper_notes(args.paper_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_note_list_project(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_notes(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0
