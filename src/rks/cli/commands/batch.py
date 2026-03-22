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
from rks.llm import ALL_EXTRACTION_MODES
from rks.providers import (
    ArxivMetadataProvider,
    CrossrefMetadataProvider,
    PubmedMetadataProvider,
)
from rks.cli._context import (
    _open_repository,
    _open_session,
    _operations,
    _paper_to_payload,
    _load_manifest,
    _resolve_manifest_path,
    _run_batch_extract_item,
    _run_batch_output_item,
    _batch_ingest_audit,
    _batch_extract_audit,
    _batch_output_audit,
)


def register(subparsers) -> None:
    batch_parser = subparsers.add_parser("batch", help="Run repeated ingestion or extraction operations.")
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command", required=True)

    batch_ingest_parser = batch_subparsers.add_parser("ingest", help="Ingest a batch manifest.")
    batch_ingest_parser.add_argument("manifest_path", type=Path, help="Path to a JSON manifest file.")
    batch_ingest_parser.set_defaults(handler=handle_batch_ingest)

    batch_extract_parser = batch_subparsers.add_parser("extract", help="Extract a stage for a batch manifest.")
    batch_extract_parser.add_argument("stage", choices=("text", "claims", "methods", "datasets", "summary"))
    batch_extract_parser.add_argument("manifest_path", type=Path, help="Path to a JSON manifest file.")
    batch_extract_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="llm-api",
        help="Execution mode for text, claims, or summary extraction.",
    )
    batch_extract_parser.set_defaults(handler=handle_batch_extract)

    batch_output_parser = batch_subparsers.add_parser("output", help="Generate outputs for a batch manifest.")
    batch_output_parser.add_argument(
        "surface",
        choices=("answer", "brief", "disagreements", "opportunities", "reading-list", "compare", "open-questions", "review-priorities"),
    )
    batch_output_parser.add_argument("manifest_path", type=Path, help="Path to a JSON manifest file.")
    batch_output_parser.set_defaults(handler=handle_batch_output)

    prepare_parser = subparsers.add_parser("prepare", help="Run higher-level preparation workflows.")
    prepare_subparsers = prepare_parser.add_subparsers(dest="prepare_command", required=True)

    prepare_paper_output_parser = prepare_subparsers.add_parser(
        "paper-output",
        help="Plan or execute the steps needed to make a paper output-ready.",
    )
    prepare_paper_output_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    prepare_paper_output_parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the missing local steps instead of only planning them.",
    )
    prepare_paper_output_parser.set_defaults(handler=handle_prepare_paper_output)


def handle_batch_ingest(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest_path)
    results = []
    failures = []
    app_config = load_app_config()
    with _open_repository() as repo:
        for item in manifest:
            try:
                source_type = item["source_type"]
                if source_type == "pdf":
                    paper = ingest_pdf(
                        repo=repo,
                        paths=load_paths(),
                        pdf_path=_resolve_manifest_path(args.manifest_path, item["path"]),
                        title=item.get("title"),
                    )
                elif source_type == "doi":
                    paper = ingest_doi_reference(
                        repo=repo,
                        paths=load_paths(),
                        doi=item["source_ref"],
                        provider=CrossrefMetadataProvider(),
                        acquire_pdf=app_config.reference_pdf_acquisition == "auto",
                    )
                elif source_type == "arxiv":
                    paper = ingest_arxiv_reference(
                        repo=repo,
                        paths=load_paths(),
                        arxiv_id=item["source_ref"],
                        provider=ArxivMetadataProvider(),
                        acquire_pdf=app_config.reference_pdf_acquisition == "auto",
                    )
                elif source_type == "pmid":
                    paper = ingest_pmid_reference(
                        repo=repo,
                        paths=load_paths(),
                        pmid=item["source_ref"],
                        provider=PubmedMetadataProvider(),
                        acquire_pdf=app_config.reference_pdf_acquisition == "auto",
                    )
                elif source_type == "url":
                    paper = ingest_url_reference(
                        repo=repo,
                        paths=load_paths(),
                        url=item["source_ref"],
                        crossref_provider=CrossrefMetadataProvider(),
                        arxiv_provider=ArxivMetadataProvider(),
                        pubmed_provider=PubmedMetadataProvider(),
                        acquire_pdf=app_config.reference_pdf_acquisition == "auto",
                    )
                else:
                    raise ValueError(f"Unsupported batch source type: {source_type}")
                results.append(_paper_to_payload(paper))
            except Exception as exc:
                failures.append({"item": item, "error": str(exc)})
    print(
        json.dumps(
            {
                "count": len(results),
                "papers": results,
                "failures": failures,
                "audit": _batch_ingest_audit(results, failures),
            },
            indent=2,
        )
    )
    return 1 if failures else 0


def handle_batch_extract(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest_path)
    results = []
    failures = []
    for item in manifest:
        paper_id = item["paper_id"] if isinstance(item, dict) else item
        mode = item.get("mode", args.mode) if isinstance(item, dict) else args.mode
        try:
            results.append(_run_batch_extract_item(args.stage, paper_id, mode))
        except Exception as exc:
            failures.append({"paper_id": paper_id, "mode": mode, "error": str(exc)})
    print(
        json.dumps(
            {
                "stage": args.stage,
                "count": len(results),
                "results": results,
                "failures": failures,
                "audit": _batch_extract_audit(args.stage, results, failures),
            },
            indent=2,
        )
    )
    return 1 if failures else 0


def handle_batch_output(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest_path)
    results = []
    failures = []
    for item in manifest:
        try:
            results.append(_run_batch_output_item(args.surface, item))
        except Exception as exc:
            failures.append({"surface": args.surface, "item": item, "error": str(exc)})
    print(
        json.dumps(
            {
                "surface": args.surface,
                "count": len(results),
                "results": results,
                "failures": failures,
                "audit": _batch_output_audit(args.surface, results, failures),
            },
            indent=2,
        )
    )
    return 1 if failures else 0


def handle_prepare_paper_output(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).prepare_paper_for_output(args.paper_id, apply=args.apply)
    print(json.dumps(payload, indent=2))
    return 0
