from __future__ import annotations

import argparse
import json

from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
from rks.cli._context import (
    _open_session,
    _paper_to_payload,
    _operations,
    _claim_subject,
    _claim_object,
    _method_payload,
    _dataset_payload,
    _edge_payload,
    _note_payload,
)


def register(subparsers) -> None:
    show_parser = subparsers.add_parser("show", help="Inspect stored research objects.")
    show_subparsers = show_parser.add_subparsers(dest="show_command", required=True)

    show_paper_parser = show_subparsers.add_parser("paper", help="Show a stored paper.")
    show_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    show_paper_parser.set_defaults(handler=handle_show_paper)

    show_claim_parser = show_subparsers.add_parser("claim", help="Show a stored claim with evidence and edges.")
    show_claim_parser.add_argument("claim_id", help="Claim ID, for example c_000001.")
    show_claim_parser.set_defaults(handler=handle_show_claim)

    show_method_parser = show_subparsers.add_parser("method", help="Show a stored method with edges.")
    show_method_parser.add_argument("method_id", help="Method ID, for example m_000001.")
    show_method_parser.set_defaults(handler=handle_show_method)

    show_dataset_parser = show_subparsers.add_parser("dataset", help="Show a stored dataset with edges.")
    show_dataset_parser.add_argument("dataset_id", help="Dataset ID, for example d_000001.")
    show_dataset_parser.set_defaults(handler=handle_show_dataset)

    show_project_parser = show_subparsers.add_parser("project", help="Show a stored research project.")
    show_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    show_project_parser.set_defaults(handler=handle_show_project)

    show_hypothesis_parser = show_subparsers.add_parser("hypothesis", help="Show a stored project hypothesis.")
    show_hypothesis_parser.add_argument("hypothesis_id", help="Hypothesis ID, for example h_000001.")
    show_hypothesis_parser.set_defaults(handler=handle_show_hypothesis)


def handle_show_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        paper = session.papers.get_paper(args.paper_id)
        artifacts = session.papers.get_artifacts_for_paper(args.paper_id)
        notes = session.notes.list_notes_for_target(target_id=args.paper_id, target_type="paper")
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = _paper_to_payload(paper)
    payload["artifacts"] = [
        {
            "id": artifact.id,
            "artifact_type": artifact.artifact_type,
            "path": artifact.path,
            "format": artifact.format,
            "metadata": json.loads(artifact.metadata_json),
            "created_at": artifact.created_at,
        }
        for artifact in artifacts
    ]
    payload["notes"] = [_note_payload(note) for note in notes]
    payload["tags"] = tags
    print(json.dumps(payload, indent=2))
    return 0


def handle_show_claim(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claim = session.claims.get_claim(args.claim_id)
        edges = session.edges.list_edges_for_claim(args.claim_id)
        query = QueryService(
            papers=session.papers,
            claims=session.claims,
            concepts=session.concepts,
            edges=session.edges,
            methods=session.methods,
            datasets=session.datasets,
            embeddings=session.embeddings,
            embedding_provider=LocalHashEmbeddingProvider(),
        )
        reviewed_relations = query.claim_relations(args.claim_id)["reviewed_relations"]
        payload = {
            "id": claim.id,
            "paper_id": claim.paper_id,
            "text": claim.text,
            "subject": _claim_subject(session.concepts, claim),
            "predicate": claim.predicate,
            "object": _claim_object(session.concepts, claim),
            "confidence": claim.confidence,
            "evidence": json.loads(claim.evidence_json or "{}"),
            "context": json.loads(claim.context_json or "{}"),
            "reviewed_relations": reviewed_relations,
            "edges": [
                {
                    "id": edge.id,
                    "source_id": edge.source_id,
                    "relation_type": edge.relation_type,
                    "target_id": edge.target_id,
                    "metadata": json.loads(edge.metadata_json or "{}"),
                }
                for edge in edges
            ],
        }
    print(json.dumps(payload, indent=2))
    return 0


def handle_show_method(args: argparse.Namespace) -> int:
    with _open_session() as session:
        method = session.methods.get_method(args.method_id)
        edges = session.edges.list_edges_for_object(args.method_id)
        payload = {
            **_method_payload(session.concepts, method),
            "edges": [_edge_payload(edge) for edge in edges],
        }
    print(json.dumps(payload, indent=2))
    return 0


def handle_show_dataset(args: argparse.Namespace) -> int:
    with _open_session() as session:
        dataset = session.datasets.get_dataset(args.dataset_id)
        edges = session.edges.list_edges_for_object(args.dataset_id)
        payload = {
            **_dataset_payload(dataset),
            "edges": [_edge_payload(edge) for edge in edges],
        }
    print(json.dumps(payload, indent=2))
    return 0


def handle_show_project(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).get_project(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_show_hypothesis(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).get_hypothesis(args.hypothesis_id)
    print(json.dumps(payload, indent=2))
    return 0
