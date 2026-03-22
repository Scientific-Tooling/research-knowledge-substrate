from __future__ import annotations

import argparse
import json

from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService, index_embeddings
from rks.cli._context import (
    _open_session,
    _operations,
    _claim_subject,
    _claim_object,
    _method_payload,
    _dataset_payload,
)


def register(subparsers) -> None:
    claims_parser = subparsers.add_parser("claims", help="List extracted claims for a paper.")
    claims_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    claims_parser.set_defaults(handler=handle_claims)

    methods_parser = subparsers.add_parser("methods", help="List extracted methods for a paper.")
    methods_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    methods_parser.set_defaults(handler=handle_methods)

    datasets_parser = subparsers.add_parser("datasets", help="List extracted datasets for a paper.")
    datasets_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    datasets_parser.set_defaults(handler=handle_datasets)

    concepts_parser = subparsers.add_parser("concepts", help="List concepts linked to a paper.")
    concepts_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    concepts_parser.set_defaults(handler=handle_concepts)

    concept_parser = subparsers.add_parser("concept", help="Manage stored concepts.")
    concept_subparsers = concept_parser.add_subparsers(dest="concept_command", required=True)

    concept_add_alias_parser = concept_subparsers.add_parser("add-alias", help="Add an alias to a concept.")
    concept_add_alias_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    concept_add_alias_parser.add_argument("alias", help="Alias term to add.")
    concept_add_alias_parser.set_defaults(handler=handle_concept_add_alias)

    concept_merge_parser = concept_subparsers.add_parser(
        "merge", help="Merge source concept into target, re-homing all claims and edges."
    )
    concept_merge_parser.add_argument("source_id", help="Concept ID to absorb and delete, for example k_000002.")
    concept_merge_parser.add_argument("target_id", help="Concept ID to keep, for example k_000001.")
    concept_merge_parser.set_defaults(handler=handle_concept_merge)

    concept_dup_parser = concept_subparsers.add_parser(
        "find-duplicates",
        help="Find concept pairs that may refer to the same entity (trigram similarity).",
    )
    concept_dup_parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="Minimum trigram similarity score (0–1). Default: 0.75.",
    )
    concept_dup_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of pairs to return. Default: 20.",
    )
    concept_dup_parser.set_defaults(handler=handle_concept_find_duplicates)

    search_parser = subparsers.add_parser("search", help="Run local text search across papers, claims, and concepts.")
    search_parser.add_argument("query", help="Search query text.")
    search_parser.add_argument(
        "--mode",
        choices=("lexical", "semantic", "hybrid"),
        default="hybrid",
        help="Search mode. Hybrid combines lexical and local semantic retrieval.",
    )
    search_parser.set_defaults(handler=handle_search)

    index_parser = subparsers.add_parser("index", help="Build local derived indexes.")
    index_subparsers = index_parser.add_subparsers(dest="index_command", required=True)

    index_embeddings_parser = index_subparsers.add_parser("embeddings", help="Index local embeddings.")
    index_embeddings_parser.add_argument("--paper-id", help="Optional paper ID to index incrementally.")
    index_embeddings_parser.set_defaults(handler=handle_index_embeddings)

    status_parser = subparsers.add_parser("status", help="Inspect workflow status.")
    status_subparsers = status_parser.add_subparsers(dest="status_command", required=True)

    status_paper_parser = status_subparsers.add_parser("paper", help="Show extraction and task status for a paper.")
    status_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    status_paper_parser.set_defaults(handler=handle_status_paper)


def handle_claims(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claims = session.claims.list_claims_for_paper(args.paper_id)
        payload = [
            {
                "id": claim.id,
                "paper_id": claim.paper_id,
                "text": claim.text,
                "subject": _claim_subject(session.concepts, claim),
                "predicate": claim.predicate,
                "object": _claim_object(session.concepts, claim),
                "confidence": claim.confidence,
                "evidence": json.loads(claim.evidence_json or "{}"),
                "created_at": claim.created_at,
            }
            for claim in claims
        ]
    print(json.dumps(payload, indent=2))
    return 0


def handle_methods(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = [_method_payload(session.concepts, method) for method in session.methods.list_methods_for_paper(args.paper_id)]
    print(json.dumps(payload, indent=2))
    return 0


def handle_datasets(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = [_dataset_payload(dataset) for dataset in session.datasets.list_datasets_for_paper(args.paper_id)]
    print(json.dumps(payload, indent=2))
    return 0


def handle_concepts(args: argparse.Namespace) -> int:
    with _open_session() as session:
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
        payload = query.concepts_for_paper(args.paper_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_concept_add_alias(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_concept_alias(args.concept_id, args.alias)
    print(json.dumps(payload, indent=2))
    return 0


def handle_concept_merge(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).merge_concepts(args.source_id, args.target_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_concept_find_duplicates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).find_duplicate_concepts(
            threshold=args.threshold,
            limit=args.limit,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_search(args: argparse.Namespace) -> int:
    with _open_session() as session:
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
        payload = query.search(args.query, mode=args.mode)
    print(json.dumps(payload, indent=2))
    return 0


def handle_index_embeddings(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = index_embeddings(
            papers=session.papers,
            claims=session.claims,
            concepts=session.concepts,
            embeddings=session.embeddings,
            paper_id=args.paper_id,
            provider=LocalHashEmbeddingProvider(),
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_status_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        operations = _operations(session)
        payload = operations.paper_status(args.paper_id)
    print(json.dumps(payload, indent=2))
    return 0
