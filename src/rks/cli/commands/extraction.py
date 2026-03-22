from __future__ import annotations

import argparse
import json

from rks.agent import (
    create_claims_request,
    create_datasets_request,
    create_extract_all_request,
    create_methods_request,
    create_summary_request,
    create_text_request,
    record_task_report,
)
from rks.config import load_llm_config, load_paths
from rks.extraction import (
    extract_all_with_llm,
    extract_claims_with_llm,
    extract_datasets_with_llm,
    extract_methods_with_llm,
    extract_text_with_llm,
)
from rks.llm import ALL_EXTRACTION_MODES, run_dual_track_mode
from rks.providers import (
    LocalHashEmbeddingProvider,
    OpenAICompatibleLlmProvider,
)
from rks.query import index_embeddings
from rks.reasoning.summary import build_summary_input, persist_summary_artifact
from rks.cli._context import (
    _open_session,
    _artifact_payload,
    _claims_payload,
    _methods_payload,
    _datasets_payload,
)


def register(subparsers) -> None:
    summarize_parser = subparsers.add_parser("summarize", help="Generate or request reasoning outputs.")
    summarize_subparsers = summarize_parser.add_subparsers(dest="summarize_command", required=True)

    summarize_paper_parser = summarize_subparsers.add_parser("paper", help="Summarize a paper.")
    summarize_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    summarize_paper_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="llm-api",
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
        default="llm-api",
        help="Execution mode for text extraction.",
    )
    extract_text_parser.set_defaults(handler=handle_extract_text)

    extract_claims_parser = extract_subparsers.add_parser("claims", help="Extract claims for a paper.")
    extract_claims_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_claims_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="llm-api",
        help="Execution mode for claim extraction.",
    )
    extract_claims_parser.set_defaults(handler=handle_extract_claims)

    extract_methods_parser = extract_subparsers.add_parser("methods", help="Extract methods for a paper.")
    extract_methods_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_methods_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="llm-api",
        help="Execution mode for method extraction.",
    )
    extract_methods_parser.set_defaults(handler=handle_extract_methods)

    extract_datasets_parser = extract_subparsers.add_parser("datasets", help="Extract datasets for a paper.")
    extract_datasets_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_datasets_parser.add_argument(
        "--mode",
        choices=ALL_EXTRACTION_MODES,
        default="llm-api",
        help="Execution mode for dataset extraction.",
    )
    extract_datasets_parser.set_defaults(handler=handle_extract_datasets)

    extract_all_parser = extract_subparsers.add_parser(
        "all", help="Single-pass combined extraction (text+claims+methods+datasets+summary) for a paper."
    )
    extract_all_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    extract_all_parser.add_argument(
        "--mode",
        choices=("llm-api", "agent"),
        default="llm-api",
        help="Execution mode: llm-api (synchronous) or agent (queue a single extract_all task).",
    )
    extract_all_parser.set_defaults(handler=handle_extract_all)


def handle_summarize_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = run_dual_track_mode(
            args.mode,
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
        if args.mode == "agent":
            task = session.tasks.create_task(
                task_type="summarize_paper",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=payload["artifact_id"],
                spec_version=payload["spec_version"],
                schema_version=payload["schema_version"],
            )
            record_task_report(session.papers, load_paths(), task, note="Queued from rks summarize paper --mode agent.")
            payload["task_id"] = task.id
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_text(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        paper = session.papers.get_paper(args.paper_id)
        payload = run_dual_track_mode(
            args.mode,
            llm_api=lambda: _artifact_payload(
                args.paper_id,
                args.mode,
                extract_text_with_llm(
                    repo=session.papers,
                    paths=paths,
                    paper=paper,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                ),
            ),
            agent=lambda: {
                **create_text_request(repo=session.papers, paths=paths, paper_id=args.paper_id),
                "mode": args.mode,
            },
        )
        if args.mode == "agent":
            task = session.tasks.create_task(
                task_type="extract_text",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=payload["artifact_id"],
                spec_version=payload["spec_version"],
                schema_version=payload["schema_version"],
            )
            record_task_report(session.papers, load_paths(), task, note="Queued from rks extract text --mode agent.")
            payload["task_id"] = task.id
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_claims(args: argparse.Namespace) -> int:
    with _open_session() as session:
        claims_payload = run_dual_track_mode(
            args.mode,
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
            task = session.tasks.create_task(
                task_type="extract_claims",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=claims_payload["artifact_id"],
                spec_version=claims_payload["spec_version"],
                schema_version=claims_payload["schema_version"],
            )
            record_task_report(session.papers, load_paths(), task, note="Queued from rks extract claims --mode agent.")
            payload = {**claims_payload, "task_id": task.id}
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_methods(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        payload = run_dual_track_mode(
            args.mode,
            llm_api=lambda: _methods_payload(
                args.paper_id,
                args.mode,
                extract_methods_with_llm(
                    paths=paths,
                    paper_repo=session.papers,
                    claim_repo=session.claims,
                    concept_repo=session.concepts,
                    edge_repo=session.edges,
                    method_repo=session.methods,
                    dataset_repo=session.datasets,
                    paper_id=args.paper_id,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                ),
            ),
            agent=lambda: {
                **create_methods_request(repo=session.papers, paths=paths, paper_id=args.paper_id),
                "mode": args.mode,
            },
        )
        if args.mode == "agent":
            task = session.tasks.create_task(
                task_type="extract_methods",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=payload["artifact_id"],
                spec_version=payload["spec_version"],
                schema_version=payload["schema_version"],
            )
            record_task_report(session.papers, paths, task, note="Queued from rks extract methods --mode agent.")
            payload = {**payload, "task_id": task.id}
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_datasets(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        payload = run_dual_track_mode(
            args.mode,
            llm_api=lambda: _datasets_payload(
                args.paper_id,
                args.mode,
                extract_datasets_with_llm(
                    paths=paths,
                    paper_repo=session.papers,
                    claim_repo=session.claims,
                    edge_repo=session.edges,
                    dataset_repo=session.datasets,
                    method_repo=session.methods,
                    paper_id=args.paper_id,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                ),
            ),
            agent=lambda: {
                **create_datasets_request(repo=session.papers, paths=paths, paper_id=args.paper_id),
                "mode": args.mode,
            },
        )
        if args.mode == "agent":
            task = session.tasks.create_task(
                task_type="extract_datasets",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=payload["artifact_id"],
                spec_version=payload["spec_version"],
                schema_version=payload["schema_version"],
            )
            record_task_report(session.papers, paths, task, note="Queued from rks extract datasets --mode agent.")
            payload = {**payload, "task_id": task.id}
    print(json.dumps(payload, indent=2))
    return 0


def handle_extract_all(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        if args.mode == "llm-api":
            counts = extract_all_with_llm(
                paths=paths,
                paper_repo=session.papers,
                claim_repo=session.claims,
                concept_repo=session.concepts,
                edge_repo=session.edges,
                method_repo=session.methods,
                dataset_repo=session.datasets,
                paper_id=args.paper_id,
                provider=OpenAICompatibleLlmProvider(load_llm_config()),
            )
            payload = {"paper_id": args.paper_id, "mode": args.mode, **counts}
        else:  # agent
            request = create_extract_all_request(repo=session.papers, paths=paths, paper_id=args.paper_id)
            task = session.tasks.create_task(
                task_type="extract_all",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=request["artifact_id"],
                spec_version=request["spec_version"],
                schema_version=request["schema_version"],
            )
            record_task_report(session.papers, paths, task, note="Queued from rks extract all --mode agent.")
            payload = {**request, "task_id": task.id, "mode": args.mode}
    print(json.dumps(payload, indent=2))
    return 0
