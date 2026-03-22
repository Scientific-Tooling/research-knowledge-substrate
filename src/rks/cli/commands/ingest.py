from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks.config import load_app_config, load_paths
from rks.ingestion import (
    ingest_arxiv_reference,
    ingest_doi_reference,
    ingest_pdf,
    ingest_pmid_reference,
    ingest_url_reference,
)
from rks.providers import (
    ArxivMetadataProvider,
    CrossrefMetadataProvider,
    PubmedMetadataProvider,
)
from rks.cli._context import (
    _open_session,
    _paper_to_payload,
    _run_pipeline_if_configured,
)


def register(subparsers) -> None:
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

    ingest_pmid_parser = ingest_subparsers.add_parser("pmid", help="Ingest a PubMed reference by PMID.")
    ingest_pmid_parser.add_argument("pmid", help="PubMed identifier, for example 31452104.")
    ingest_pmid_parser.set_defaults(handler=handle_ingest_pmid)

    ingest_url_parser = ingest_subparsers.add_parser(
        "url",
        help="Ingest a paper from a canonical reference URL or direct PDF URL.",
    )
    ingest_url_parser.add_argument("url", help="DOI, arXiv, PubMed, or direct PDF URL.")
    ingest_url_parser.set_defaults(handler=handle_ingest_url)


def handle_ingest_pdf(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        paper = ingest_pdf(repo=session.papers, paths=paths, pdf_path=args.path, title=args.title)
        pipeline = _run_pipeline_if_configured(session, paths, paper.id)
    payload = _paper_to_payload(paper)
    if pipeline:
        payload["pipeline"] = pipeline
    print(json.dumps(payload, indent=2))
    return 0


def handle_ingest_doi(args: argparse.Namespace) -> int:
    paths = load_paths()
    app_config = load_app_config()
    with _open_session() as session:
        paper = ingest_doi_reference(
            repo=session.papers,
            paths=paths,
            doi=args.doi,
            provider=CrossrefMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
        pipeline = _run_pipeline_if_configured(session, paths, paper.id)
    payload = _paper_to_payload(paper)
    if pipeline:
        payload["pipeline"] = pipeline
    print(json.dumps(payload, indent=2))
    return 0


def handle_ingest_arxiv(args: argparse.Namespace) -> int:
    paths = load_paths()
    app_config = load_app_config()
    with _open_session() as session:
        paper = ingest_arxiv_reference(
            repo=session.papers,
            paths=paths,
            arxiv_id=args.arxiv_id,
            provider=ArxivMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
        pipeline = _run_pipeline_if_configured(session, paths, paper.id)
    payload = _paper_to_payload(paper)
    if pipeline:
        payload["pipeline"] = pipeline
    print(json.dumps(payload, indent=2))
    return 0


def handle_ingest_pmid(args: argparse.Namespace) -> int:
    paths = load_paths()
    app_config = load_app_config()
    with _open_session() as session:
        paper = ingest_pmid_reference(
            repo=session.papers,
            paths=paths,
            pmid=args.pmid,
            provider=PubmedMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
        pipeline = _run_pipeline_if_configured(session, paths, paper.id)
    payload = _paper_to_payload(paper)
    if pipeline:
        payload["pipeline"] = pipeline
    print(json.dumps(payload, indent=2))
    return 0


def handle_ingest_url(args: argparse.Namespace) -> int:
    paths = load_paths()
    app_config = load_app_config()
    with _open_session() as session:
        paper = ingest_url_reference(
            repo=session.papers,
            paths=paths,
            url=args.url,
            crossref_provider=CrossrefMetadataProvider(),
            arxiv_provider=ArxivMetadataProvider(),
            pubmed_provider=PubmedMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
        pipeline = _run_pipeline_if_configured(session, paths, paper.id)
    payload = _paper_to_payload(paper)
    if pipeline:
        payload["pipeline"] = pipeline
    print(json.dumps(payload, indent=2))
    return 0
