from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from rks.cli._context import _open_session, _operations
from rks.config import load_paths
from rks.operations.evidence_import import import_evidence, require_schema, resolve_paper
from rks.operations.evidence_search import search_evidence
from rks.storage.db import connect_db_readonly
from rks.storage.evidence_repository import EvidenceRepository


def register(subparsers) -> None:
    note_parser = subparsers.add_parser("note", help="Add or inspect user and agent notes.")
    note_subparsers = note_parser.add_subparsers(dest="note_command", required=True)

    evidence = note_subparsers.add_parser("import-evidence", help="Preview or atomically apply selected APW evidence.")
    evidence.add_argument("bundle", type=Path)
    evidence.add_argument("--workspace-id", required=True)
    evidence.add_argument("--apply", action="store_true", help="Apply an exact dry-run plan; default is read-only preview.")
    evidence.add_argument("--plan", type=Path, help="Previously saved dry-run JSON, required for --apply.")
    evidence.add_argument("--accept-updates", action="store_true", help="Explicitly accept previewed revision changes.")
    evidence.set_defaults(handler=handle_import_evidence)
    evidence_list = note_subparsers.add_parser("evidence", help="Read imported evidence and its revision history.")
    evidence_list.add_argument("paper_id")
    evidence_list.set_defaults(handler=handle_evidence_list)

    search = note_subparsers.add_parser("search-evidence", help="Search current imported evidence within exact paper sources.")
    search.add_argument("query")
    search.add_argument("--workspace-id", required=True)
    search.add_argument("--source-id", required=True)
    search.add_argument("--paper-source", action="append", required=True, help="paper_id:document_sha256; repeat for each source.")
    search.add_argument("--review", choices=("all", "reviewed", "unreviewed"), default="all")
    search.add_argument("--mode", choices=("lexical", "phrase"), default="lexical")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--offset", type=int, default=0)
    search.set_defaults(handler=handle_evidence_search)

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


def handle_import_evidence(args: argparse.Namespace) -> int:
    bundle = json.loads(args.bundle.read_text(encoding="utf-8-sig"))
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig")) if args.plan else None
    db_path = load_paths().db_path
    # Do not create or migrate a database on either the preview or apply path.
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode={'rw' if args.apply else 'ro'}", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        payload = import_evidence(conn, bundle, workspace_id=args.workspace_id, plan=plan,
                                  apply=args.apply, accept_updates=args.accept_updates)
    print(json.dumps(payload, indent=2))
    return 2 if payload["counts"]["conflict"] else 0


def handle_evidence_list(args: argparse.Namespace) -> int:
    with closing(connect_db_readonly(load_paths().db_path)) as conn:
        require_schema(conn)
        conn.execute("BEGIN")
        paper_id = resolve_paper(conn, args.paper_id)
        records = EvidenceRepository(conn).list_for_paper(paper_id)
    print(json.dumps({"paper_id": paper_id, "evidence": records}, indent=2))
    return 0


def handle_evidence_search(args: argparse.Namespace) -> int:
    with closing(connect_db_readonly(load_paths().db_path)) as conn:
        conn.execute("BEGIN")
        payload = search_evidence(conn, args.query, workspace_id=args.workspace_id, source_id=args.source_id,
                                  paper_sources=args.paper_source, review=args.review, mode=args.mode,
                                  limit=args.limit, offset=args.offset)
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
