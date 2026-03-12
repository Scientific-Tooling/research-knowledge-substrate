from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks.config import load_paths
from rks.extraction import extract_claims_for_paper, extract_text_for_paper
from rks.ingestion import ingest_arxiv_reference, ingest_doi_reference, ingest_pdf
from rks.providers import ArxivMetadataProvider, CrossrefMetadataProvider
from rks.query import QueryService
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    EdgeRepository,
    PaperRepository,
    connect_db,
    initialize_db,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Initialize the local RKS SQLite database.")
    init_parser.set_defaults(handler=handle_init_db)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest research sources.")
    ingest_subparsers = ingest_parser.add_subparsers(dest="ingest_command", required=True)

    ingest_pdf_parser = ingest_subparsers.add_parser("pdf", help="Ingest a local PDF into RKS.")
    ingest_pdf_parser.add_argument("path", type=Path, help="Path to a local PDF file.")
    ingest_pdf_parser.add_argument("--title", help="Optional paper title override.")
    ingest_pdf_parser.set_defaults(handler=handle_ingest_pdf)

    ingest_doi_parser = ingest_subparsers.add_parser("doi", help="Ingest a DOI reference.")
    ingest_doi_parser.add_argument("doi", help="DOI value, for example 10.48550/arXiv.1706.03762.")
    ingest_doi_parser.set_defaults(handler=handle_ingest_doi)

    ingest_arxiv_parser = ingest_subparsers.add_parser("arxiv", help="Ingest an arXiv reference.")
    ingest_arxiv_parser.add_argument("arxiv_id", help="arXiv identifier, for example 1706.03762.")
    ingest_arxiv_parser.set_defaults(handler=handle_ingest_arxiv)

    show_parser = subparsers.add_parser("show", help="Inspect stored research objects.")
    show_subparsers = show_parser.add_subparsers(dest="show_command", required=True)

    show_paper_parser = show_subparsers.add_parser("paper", help="Show a stored paper.")
    show_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    show_paper_parser.set_defaults(handler=handle_show_paper)

    show_claim_parser = show_subparsers.add_parser("claim", help="Show a stored claim with evidence and edges.")
    show_claim_parser.add_argument("claim_id", help="Claim ID, for example c_000001.")
    show_claim_parser.set_defaults(handler=handle_show_claim)

    claims_parser = subparsers.add_parser("claims", help="List extracted claims for a paper.")
    claims_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    claims_parser.set_defaults(handler=handle_claims)

    concepts_parser = subparsers.add_parser("concepts", help="List concepts linked to a paper.")
    concepts_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    concepts_parser.set_defaults(handler=handle_concepts)

    extract_parser = subparsers.add_parser("extract", help="Run extraction steps for a stored paper.")
    extract_subparsers = extract_parser.add_subparsers(dest="extract_command", required=True)

    extract_text_parser = extract_subparsers.add_parser("text", help="Extract text artifacts for a paper.")
    extract_text_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_text_parser.set_defaults(handler=handle_extract_text)

    extract_claims_parser = extract_subparsers.add_parser("claims", help="Extract heuristic claims for a paper.")
    extract_claims_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_claims_parser.set_defaults(handler=handle_extract_claims)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


def handle_init_db(args: argparse.Namespace) -> int:
    del args
    with _open_repository() as repo:
        print(json.dumps({"status": "ok", "db_initialized": True}, indent=2))
    return 0


def handle_ingest_pdf(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        paper = ingest_pdf(repo=repo, paths=load_paths(), pdf_path=args.path, title=args.title)
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_ingest_doi(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        paper = ingest_doi_reference(
            repo=repo,
            paths=load_paths(),
            doi=args.doi,
            provider=CrossrefMetadataProvider(),
        )
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_ingest_arxiv(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        paper = ingest_arxiv_reference(
            repo=repo,
            paths=load_paths(),
            arxiv_id=args.arxiv_id,
            provider=ArxivMetadataProvider(),
        )
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_show_paper(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        paper = repo.get_paper(args.paper_id)
        artifacts = repo.get_artifacts_for_paper(args.paper_id)
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
    print(json.dumps(payload, indent=2))
    return 0


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


def handle_concepts(args: argparse.Namespace) -> int:
    with _open_session() as session:
        query = QueryService(
            papers=session.papers,
            claims=session.claims,
            concepts=session.concepts,
            edges=session.edges,
        )
        payload = query.concepts_for_paper(args.paper_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_show_claim(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claim = session.claims.get_claim(args.claim_id)
        edges = session.edges.list_edges_for_claim(args.claim_id)
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


def handle_extract_text(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_repository() as repo:
        paper = repo.get_paper(args.paper_id)
        artifact = extract_text_for_paper(repo=repo, paths=paths, paper=paper)
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


def handle_extract_claims(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claims = extract_claims_for_paper(
            paths=load_paths(),
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            paper_id=args.paper_id,
        )
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "claim_count": len(claims),
                "claim_ids": [claim.id for claim in claims],
            },
            indent=2,
        )
    )
    return 0


def handle_query_claims_about(args: argparse.Namespace) -> int:
    with _open_session() as session:
        query = QueryService(
            papers=session.papers,
            claims=session.claims,
            concepts=session.concepts,
            edges=session.edges,
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
        )
        payload = query.papers_supporting(args.claim_id)
    print(json.dumps(payload, indent=2))
    return 0


class _RepositoryContext:
    def __enter__(self) -> PaperRepository:
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return PaperRepository(self.conn)

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.conn.rollback()
        self.conn.close()


def _open_repository() -> _RepositoryContext:
    return _RepositoryContext()


class _Session:
    def __init__(
        self,
        papers: PaperRepository,
        claims: ClaimRepository,
        concepts: ConceptRepository,
        edges: EdgeRepository,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.edges = edges


class _SessionContext:
    def __enter__(self) -> _Session:
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return _Session(
            papers=PaperRepository(self.conn),
            claims=ClaimRepository(self.conn),
            concepts=ConceptRepository(self.conn),
            edges=EdgeRepository(self.conn),
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.conn.rollback()
        self.conn.close()


def _open_session() -> _SessionContext:
    return _SessionContext()


def _paper_to_payload(paper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": json.loads(paper.authors_json),
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "source_type": paper.source_type,
        "source_ref": paper.source_ref,
        "pdf_path": paper.pdf_path,
        "text_artifact_id": paper.text_artifact_id,
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
    }


def _claim_subject(concepts: ConceptRepository, claim) -> str | None:
    context = json.loads(claim.context_json or "{}")
    if claim.subject_concept_id:
        return concepts.get_concept(claim.subject_concept_id).name
    return context.get("subject_text")


def _claim_object(concepts: ConceptRepository, claim) -> str | None:
    if claim.object_concept_id:
        return concepts.get_concept(claim.object_concept_id).name
    return claim.object_text
