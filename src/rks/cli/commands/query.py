from __future__ import annotations

import argparse
import json

from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
from rks.cli._context import _open_session, _operations


def register(subparsers) -> None:
    query_parser = subparsers.add_parser("query", help="Run deterministic research graph queries.")
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    query_claims_about_parser = query_subparsers.add_parser("claims-about", help="List claims about a concept.")
    query_claims_about_parser.add_argument("concept", help="Concept name or concept ID.")
    query_claims_about_parser.set_defaults(handler=handle_query_claims_about)

    query_papers_supporting_parser = query_subparsers.add_parser(
        "papers-supporting",
        help="List papers supporting a claim.",
    )
    query_papers_supporting_parser.add_argument("claim_id", help="Claim ID, for example c_000001.")
    query_papers_supporting_parser.set_defaults(handler=handle_query_papers_supporting)

    query_evidence_for_parser = query_subparsers.add_parser("evidence-for", help="Aggregate evidence for a concept or claim.")
    query_evidence_for_parser.add_argument("target", help="Concept name, concept ID, or claim ID.")
    query_evidence_for_parser.set_defaults(handler=handle_query_evidence_for)

    query_claim_relations_parser = query_subparsers.add_parser(
        "claim-relations",
        help="List support/refinement/contradiction patterns around a claim.",
    )
    query_claim_relations_parser.add_argument("claim_id", help="Claim ID, for example c_000001.")
    query_claim_relations_parser.set_defaults(handler=handle_query_claim_relations)

    query_methods_for_parser = query_subparsers.add_parser("methods-for", help="List methods for a paper or concept.")
    query_methods_for_parser.add_argument("target", help="Paper ID or concept name.")
    query_methods_for_parser.set_defaults(handler=handle_query_methods_for)

    query_datasets_for_parser = query_subparsers.add_parser("datasets-for", help="List datasets for a paper or method.")
    query_datasets_for_parser.add_argument("target", help="Paper ID or method ID.")
    query_datasets_for_parser.set_defaults(handler=handle_query_datasets_for)

    query_review_priorities_parser = query_subparsers.add_parser(
        "review-priorities", help="Rank pending candidates by evolution-derived priority."
    )
    query_review_priorities_parser.add_argument("--scope-type", default="concept", choices=("concept", "project"))
    query_review_priorities_parser.add_argument("--scope-id", default=None, help="Optional project or concept ID to scope.")
    query_review_priorities_parser.set_defaults(handler=handle_query_review_priorities)

    query_open_questions_parser = query_subparsers.add_parser(
        "open-questions", help="Identify evidence-sparse controversies and under-explored areas."
    )
    query_open_questions_parser.add_argument("--scope-type", default="concept", choices=("concept", "project"))
    query_open_questions_parser.add_argument("--scope-id", default=None, help="Optional project or concept ID to scope.")
    query_open_questions_parser.set_defaults(handler=handle_query_open_questions)

    query_concept_controversies_parser = query_subparsers.add_parser(
        "concept-controversies", help="Rank concepts by controversy score (descending)."
    )
    query_concept_controversies_parser.add_argument("--min-score", type=float, default=0.0, help="Minimum controversy score filter (0.0–1.0).")
    query_concept_controversies_parser.add_argument("--limit", type=int, default=50, help="Maximum number of results to return.")
    query_concept_controversies_parser.set_defaults(handler=handle_query_concept_controversies)


def handle_query_claims_about(args: argparse.Namespace) -> int:
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
        payload = query.claims_about(args.concept)
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_papers_supporting(args: argparse.Namespace) -> int:
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
        payload = query.papers_supporting(args.claim_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_evidence_for(args: argparse.Namespace) -> int:
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
        payload = query.evidence_for(args.target)
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_claim_relations(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).claim_relations(args.claim_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_methods_for(args: argparse.Namespace) -> int:
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
        payload = query.methods_for(args.target)
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_datasets_for(args: argparse.Namespace) -> int:
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
        payload = query.datasets_for(args.target)
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_review_priorities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).compute_review_priorities(
            scope_type=args.scope_type,
            scope_id=args.scope_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_open_questions(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).compute_open_questions(
            scope_type=args.scope_type,
            scope_id=args.scope_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_query_concept_controversies(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_concept_controversies(
            min_score=args.min_score,
            limit=args.limit,
        )
    print(json.dumps(payload, indent=2))
    return 0
