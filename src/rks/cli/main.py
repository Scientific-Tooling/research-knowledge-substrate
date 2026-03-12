from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks.agent import (
    create_claims_request,
    create_summary_request,
    create_text_request,
    import_claims_result,
    import_summary_result,
    import_text_result,
)
from rks.config import load_paths
from rks.config import load_llm_config
from rks.extraction import (
    extract_claims_for_paper,
    extract_claims_with_llm,
    extract_datasets_for_paper,
    extract_methods_for_paper,
    extract_text_for_paper,
    extract_text_with_llm,
)
from rks.ingestion import ingest_arxiv_reference, ingest_doi_reference, ingest_pdf
from rks.llm import ALL_EXTRACTION_MODES, run_dual_track_mode
from rks.providers import ArxivMetadataProvider, CrossrefMetadataProvider, LocalHashEmbeddingProvider, OpenAICompatibleLlmProvider
from rks.query import QueryService, index_embeddings
from rks.reasoning import summarize_paper_heuristic
from rks.reasoning.summary import build_summary_input, persist_summary_artifact
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    DatasetRepository,
    EmbeddingRepository,
    EdgeRepository,
    MethodRepository,
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

    show_method_parser = show_subparsers.add_parser("method", help="Show a stored method with edges.")
    show_method_parser.add_argument("method_id", help="Method ID, for example m_000001.")
    show_method_parser.set_defaults(handler=handle_show_method)

    show_dataset_parser = show_subparsers.add_parser("dataset", help="Show a stored dataset with edges.")
    show_dataset_parser.add_argument("dataset_id", help="Dataset ID, for example d_000001.")
    show_dataset_parser.set_defaults(handler=handle_show_dataset)

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

    summarize_parser = subparsers.add_parser("summarize", help="Generate or request reasoning outputs.")
    summarize_subparsers = summarize_parser.add_subparsers(dest="summarize_command", required=True)

    summarize_paper_parser = summarize_subparsers.add_parser("paper", help="Summarize a paper.")
    summarize_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    summarize_paper_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="heuristic",
        help="Execution mode for paper summarization.",
    )
    summarize_paper_parser.set_defaults(handler=handle_summarize_paper)

    extract_parser = subparsers.add_parser("extract", help="Run extraction steps for a stored paper.")
    extract_subparsers = extract_parser.add_subparsers(dest="extract_command", required=True)

    extract_text_parser = extract_subparsers.add_parser("text", help="Extract text artifacts for a paper.")
    extract_text_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_text_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="heuristic",
        help="Execution mode for text extraction.",
    )
    extract_text_parser.set_defaults(handler=handle_extract_text)

    extract_claims_parser = extract_subparsers.add_parser("claims", help="Extract heuristic claims for a paper.")
    extract_claims_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_claims_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="heuristic",
        help="Execution mode for claim extraction.",
    )
    extract_claims_parser.set_defaults(handler=handle_extract_claims)

    extract_methods_parser = extract_subparsers.add_parser("methods", help="Extract methods for a paper.")
    extract_methods_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_methods_parser.set_defaults(handler=handle_extract_methods)

    extract_datasets_parser = extract_subparsers.add_parser("datasets", help="Extract datasets for a paper.")
    extract_datasets_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_datasets_parser.set_defaults(handler=handle_extract_datasets)

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

    import_summary_parser = import_subparsers.add_parser("summary", help="Import a paper summary JSON for a paper.")
    import_summary_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_summary_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_summary_parser.set_defaults(handler=handle_import_summary)

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


def handle_summarize_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = run_dual_track_mode(
            args.mode,
            heuristic=lambda: summarize_paper_heuristic(
                paths=load_paths(),
                paper_repo=session.papers,
                claim_repo=session.claims,
                concept_repo=session.concepts,
                paper_id=args.paper_id,
            ),
            llm_api=lambda: persist_summary_artifact(
                paper_repo=session.papers,
                paths=load_paths(),
                paper_id=args.paper_id,
                payload={
                    **OpenAICompatibleLlmProvider(load_llm_config()).summarize_paper(
                        build_summary_input(session.papers, session.claims, session.concepts, args.paper_id)
                    ),
                    "mode": "llm-api",
                },
                artifact_type="paper_summary",
                filename="paper_summary.json",
            ),
            agent=lambda: {
                **create_summary_request(
                    repo=session.papers,
                    claim_repo=session.claims,
                    concept_repo=session.concepts,
                    paths=load_paths(),
                    paper_id=args.paper_id,
                ),
                "mode": "agent",
            },
        )
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


def handle_extract_text(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_repository() as repo:
        paper = repo.get_paper(args.paper_id)
        payload = run_dual_track_mode(
            args.mode,
            heuristic=lambda: _artifact_payload(
                args.paper_id,
                args.mode,
                extract_text_for_paper(repo=repo, paths=paths, paper=paper),
            ),
            llm_api=lambda: _artifact_payload(
                args.paper_id,
                args.mode,
                extract_text_with_llm(
                    repo=repo,
                    paths=paths,
                    paper=paper,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                ),
            ),
            agent=lambda: {
                **create_text_request(repo=repo, paths=paths, paper_id=args.paper_id),
                "mode": args.mode,
            },
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_claims(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claims_payload = run_dual_track_mode(
            args.mode,
            heuristic=lambda: _claims_payload(
                args.paper_id,
                args.mode,
                extract_claims_for_paper(
                    paths=load_paths(),
                    paper_repo=session.papers,
                    claim_repo=session.claims,
                    concept_repo=session.concepts,
                    edge_repo=session.edges,
                    paper_id=args.paper_id,
                ),
            ),
            llm_api=lambda: _claims_payload(
                args.paper_id,
                args.mode,
                extract_claims_with_llm(
                    paths=load_paths(),
                    paper_repo=session.papers,
                    claim_repo=session.claims,
                    concept_repo=session.concepts,
                    edge_repo=session.edges,
                    paper_id=args.paper_id,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                ),
            ),
            agent=lambda: {
                **create_claims_request(repo=session.papers, paths=load_paths(), paper_id=args.paper_id),
                "mode": args.mode,
            },
        )
        if args.mode != "agent":
            index_payload = index_embeddings(
                papers=session.papers,
                claims=session.claims,
                concepts=session.concepts,
                embeddings=session.embeddings,
                paper_id=args.paper_id,
                provider=LocalHashEmbeddingProvider(),
            )
            payload = {**claims_payload, "embedding_index": index_payload}
        else:
            payload = claims_payload
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_methods(args: argparse.Namespace) -> int:
    with _open_session() as session:
        methods = extract_methods_for_paper(
            paths=load_paths(),
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            method_repo=session.methods,
            dataset_repo=session.datasets,
            paper_id=args.paper_id,
        )
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "method_count": len(methods),
                "method_ids": [method.id for method in methods],
            },
            indent=2,
        )
    )
    return 0


def handle_extract_datasets(args: argparse.Namespace) -> int:
    with _open_session() as session:
        datasets = extract_datasets_for_paper(
            paths=load_paths(),
            paper_repo=session.papers,
            claim_repo=session.claims,
            edge_repo=session.edges,
            dataset_repo=session.datasets,
            method_repo=session.methods,
            paper_id=args.paper_id,
        )
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "dataset_count": len(datasets),
                "dataset_ids": [dataset.id for dataset in datasets],
            },
            indent=2,
        )
    )
    return 0


def handle_import_text(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        artifact = import_text_result(repo=repo, paths=load_paths(), paper_id=args.paper_id, json_path=args.json_path)
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


def handle_import_summary(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        payload = import_summary_result(repo=repo, paths=load_paths(), paper_id=args.paper_id, json_path=args.json_path)
    print(json.dumps(payload, indent=2))
    return 0


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
        payload = query.claim_relations(args.claim_id)
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
        methods: MethodRepository,
        datasets: DatasetRepository,
        embeddings: EmbeddingRepository,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings


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
            methods=MethodRepository(self.conn),
            datasets=DatasetRepository(self.conn),
            embeddings=EmbeddingRepository(self.conn),
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


def _artifact_payload(paper_id: str, mode: str, artifact) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
    }


def _claims_payload(paper_id: str, mode: str, claims: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "claim_count": len(claims),
        "claim_ids": [claim.id for claim in claims],
    }


def _method_payload(concepts: ConceptRepository, method) -> dict:
    about_concept = concepts.get_concept(method.about_concept_id).name if method.about_concept_id else None
    return {
        "id": method.id,
        "paper_id": method.paper_id,
        "name": method.name,
        "description": method.description,
        "about_concept": about_concept,
        "created_at": method.created_at,
    }


def _dataset_payload(dataset) -> dict:
    return {
        "id": dataset.id,
        "paper_id": dataset.paper_id,
        "name": dataset.name,
        "description": dataset.description,
        "source": dataset.source,
        "created_at": dataset.created_at,
    }


def _edge_payload(edge) -> dict:
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "source_type": edge.source_type,
        "relation_type": edge.relation_type,
        "target_id": edge.target_id,
        "target_type": edge.target_type,
        "metadata": json.loads(edge.metadata_json or "{}"),
    }
