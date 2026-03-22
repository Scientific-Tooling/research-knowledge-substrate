from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks.agent import (
    import_claims_result,
    import_datasets_result,
    import_extract_all_result,
    import_methods_result,
    import_summary_result,
    import_text_result,
    record_task_report,
)
from rks.config import load_paths
from rks.providers import LocalHashEmbeddingProvider
from rks.query import index_embeddings
from rks.storage import import_graph_snapshot
from rks.storage.workspace import import_workspace
from rks.cli._context import (
    _open_session,
    _artifact_id_for_type,
    _methods_payload,
    _datasets_payload,
)


def register(subparsers) -> None:
    import_parser = subparsers.add_parser("import", help="Import externally produced extraction results.")
    import_subparsers = import_parser.add_subparsers(dest="import_command", required=True)

    import_text_parser = import_subparsers.add_parser("text", help="Import extracted text JSON for a paper.")
    import_text_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_text_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_text_parser.set_defaults(handler=handle_import_text)

    import_claims_parser = import_subparsers.add_parser("claims", help="Import structured claims JSON for a paper.")
    import_claims_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_claims_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_claims_parser.set_defaults(handler=handle_import_claims)

    import_methods_parser = import_subparsers.add_parser("methods", help="Import extracted methods JSON for a paper.")
    import_methods_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_methods_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_methods_parser.set_defaults(handler=handle_import_methods)

    import_datasets_parser = import_subparsers.add_parser("datasets", help="Import extracted datasets JSON for a paper.")
    import_datasets_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_datasets_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_datasets_parser.set_defaults(handler=handle_import_datasets)

    import_summary_parser = import_subparsers.add_parser("summary", help="Import a paper summary JSON for a paper.")
    import_summary_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_summary_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_summary_parser.set_defaults(handler=handle_import_summary)

    import_all_parser = import_subparsers.add_parser(
        "all", help="Import a combined paper.v1 extraction result (text+claims+methods+datasets+summary)."
    )
    import_all_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_all_parser.add_argument("json_path", type=Path, help="Path to a paper.v1 JSON file produced by an agent.")
    import_all_parser.set_defaults(handler=handle_import_all)

    import_graph_parser = import_subparsers.add_parser("graph", help="Import a graph snapshot JSON file.")
    import_graph_parser.add_argument("json_path", type=Path, help="Path to a graph snapshot JSON file.")
    import_graph_parser.set_defaults(handler=handle_import_graph)

    import_workspace_parser = import_subparsers.add_parser(
        "workspace", help="Import a full workspace archive (.tar.gz) into the current data directory."
    )
    import_workspace_parser.add_argument(
        "archive_path", type=Path, help="Path to a workspace archive produced by `rks export workspace`."
    )
    import_workspace_parser.set_defaults(handler=handle_import_workspace)


def handle_import_all(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        counts = import_extract_all_result(
            paths=paths,
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            method_repo=session.methods,
            dataset_repo=session.datasets,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_all", None)
        if task is not None:
            record_task_report(session.papers, paths, task, note="Imported agent combined result.")
    print(json.dumps({"paper_id": args.paper_id, "mode": "agent", **counts}, indent=2))
    return 0


def handle_import_text(args: argparse.Namespace) -> int:
    with _open_session() as session:
        artifact = import_text_result(
            repo=session.papers,
            paths=load_paths(),
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_text", artifact.id)
        if task is not None:
            record_task_report(session.papers, load_paths(), task, note="Imported agent text result.")
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "artifact_id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "path": artifact.path,
            },
            indent=2,
        )
    )
    return 0


def handle_import_claims(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claims = import_claims_result(
            paths=load_paths(),
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        index_payload = index_embeddings(
            papers=session.papers,
            claims=session.claims,
            concepts=session.concepts,
            embeddings=session.embeddings,
            paper_id=args.paper_id,
            provider=LocalHashEmbeddingProvider(),
        )
        structured_claims_artifact = _artifact_id_for_type(session.papers, args.paper_id, "structured_claims")
        task = session.tasks.complete_latest_task(args.paper_id, "extract_claims", structured_claims_artifact)
        if task is not None:
            record_task_report(session.papers, load_paths(), task, note="Imported agent claims result.")
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "claim_count": len(claims),
                "claim_ids": [claim.id for claim in claims],
                "embedding_index": index_payload,
            },
            indent=2,
        )
    )
    return 0


def handle_import_methods(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        methods = import_methods_result(
            paths=paths,
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            method_repo=session.methods,
            dataset_repo=session.datasets,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_methods", None)
        if task is not None:
            record_task_report(session.papers, paths, task, note="Imported agent methods result.")
    print(json.dumps(_methods_payload(args.paper_id, "agent", methods), indent=2))
    return 0


def handle_import_datasets(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        datasets = import_datasets_result(
            paths=paths,
            paper_repo=session.papers,
            claim_repo=session.claims,
            edge_repo=session.edges,
            dataset_repo=session.datasets,
            method_repo=session.methods,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_datasets", None)
        if task is not None:
            record_task_report(session.papers, paths, task, note="Imported agent datasets result.")
    print(json.dumps(_datasets_payload(args.paper_id, "agent", datasets), indent=2))
    return 0


def handle_import_summary(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = import_summary_result(
            repo=session.papers,
            paths=load_paths(),
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "summarize_paper", payload["artifact_id"])
        if task is not None:
            record_task_report(session.papers, load_paths(), task, note="Imported agent summary result.")
    print(json.dumps(payload, indent=2))
    return 0


def handle_import_graph(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = import_graph_snapshot(session.papers.conn, args.json_path)
    print(json.dumps(payload, indent=2))
    return 0


def handle_import_workspace(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        payload = import_workspace(session.papers.conn, paths.data_dir, args.archive_path)
    print(json.dumps(payload, indent=2))
    return 0
