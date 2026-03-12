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
from rks.agent_skills import export_bundled_skills, list_bundled_skills
from rks.config import config_path, load_app_config, load_llm_config, load_paths, write_default_config
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
from rks.operations import ResearchOperations
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
    NoteRepository,
    PaperRepository,
    TaskRepository,
    connect_db,
    export_graph_snapshot,
    import_graph_snapshot,
    initialize_db,
)
from rks.storage.db import apply_migrations, current_schema_version
from rks.service import serve_http


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Initialize the local RKS SQLite database.")
    init_parser.set_defaults(handler=handle_init_db)

    config_parser = subparsers.add_parser("config", help="Manage RKS configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_init_parser = config_subparsers.add_parser("init", help="Write a default config file into the workspace root.")
    config_init_parser.set_defaults(handler=handle_config_init)

    config_show_parser = config_subparsers.add_parser("show", help="Show the effective merged config.")
    config_show_parser.set_defaults(handler=handle_config_show)

    skills_parser = subparsers.add_parser("skills", help="Inspect or export bundled agent skills.")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)

    skills_list_parser = skills_subparsers.add_parser("list", help="List bundled agent skills.")
    skills_list_parser.set_defaults(handler=handle_skills_list)

    skills_export_parser = skills_subparsers.add_parser("export", help="Export bundled agent skills to a directory.")
    skills_export_parser.add_argument("destination", type=Path, help="Directory to write the exported skill bundle into.")
    skills_export_parser.set_defaults(handler=handle_skills_export)

    migrate_parser = subparsers.add_parser("migrate", help="Apply schema migrations and report the current version.")
    migrate_parser.set_defaults(handler=handle_migrate)

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
        default="heuristic",
        help="Execution mode for text, claims, or summary extraction.",
    )
    batch_extract_parser.set_defaults(handler=handle_batch_extract)

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

    note_parser = subparsers.add_parser("note", help="Add or inspect user and agent notes.")
    note_subparsers = note_parser.add_subparsers(dest="note_command", required=True)

    note_add_parser = note_subparsers.add_parser("add", help="Add a note to a stored object.")
    note_add_subparsers = note_add_parser.add_subparsers(dest="note_target", required=True)
    note_add_paper_parser = note_add_subparsers.add_parser("paper", help="Add a note to a paper.")
    note_add_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    note_add_paper_parser.add_argument("--content", required=True, help="Note text to store.")
    note_add_paper_parser.add_argument("--created-by", default="human:user", help="Note author label.")
    note_add_paper_parser.set_defaults(handler=handle_note_add_paper)

    note_list_parser = note_subparsers.add_parser("list", help="List notes for a stored object.")
    note_list_subparsers = note_list_parser.add_subparsers(dest="note_target", required=True)
    note_list_paper_parser = note_list_subparsers.add_parser("paper", help="List notes for a paper.")
    note_list_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    note_list_paper_parser.set_defaults(handler=handle_note_list_paper)

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

    status_parser = subparsers.add_parser("status", help="Inspect workflow status.")
    status_subparsers = status_parser.add_subparsers(dest="status_command", required=True)

    status_paper_parser = status_subparsers.add_parser("paper", help="Show extraction and task status for a paper.")
    status_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    status_paper_parser.set_defaults(handler=handle_status_paper)

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

    import_graph_parser = import_subparsers.add_parser("graph", help="Import a graph snapshot JSON file.")
    import_graph_parser.add_argument("json_path", type=Path, help="Path to a graph snapshot JSON file.")
    import_graph_parser.set_defaults(handler=handle_import_graph)

    export_parser = subparsers.add_parser("export", help="Export graph data.")
    export_subparsers = export_parser.add_subparsers(dest="export_command", required=True)

    export_graph_parser = export_subparsers.add_parser("graph", help="Export a graph snapshot JSON file.")
    export_graph_parser.add_argument("json_path", type=Path, help="Destination path for the graph snapshot.")
    export_graph_parser.set_defaults(handler=handle_export_graph)

    serve_parser = subparsers.add_parser("serve", help="Run the local RKS API and lightweight UI.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.set_defaults(handler=handle_serve)

    tasks_parser = subparsers.add_parser("tasks", help="Inspect or update queued agent tasks.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command", required=True)

    tasks_list_parser = tasks_subparsers.add_parser("list", help="List queued, completed, or failed tasks.")
    tasks_list_parser.add_argument("--paper-id", help="Filter by paper ID.")
    tasks_list_parser.add_argument("--status", help="Filter by status.")
    tasks_list_parser.set_defaults(handler=handle_tasks_list)

    tasks_show_parser = tasks_subparsers.add_parser("show", help="Show one task.")
    tasks_show_parser.add_argument("task_id", help="Task ID, for example t_000001.")
    tasks_show_parser.set_defaults(handler=handle_tasks_show)

    tasks_fail_parser = tasks_subparsers.add_parser("fail", help="Mark a task as failed.")
    tasks_fail_parser.add_argument("task_id", help="Task ID, for example t_000001.")
    tasks_fail_parser.add_argument("message", help="Failure message to record.")
    tasks_fail_parser.set_defaults(handler=handle_tasks_fail)

    review_parser = subparsers.add_parser("review", help="Promote or retract reviewed graph facts.")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    review_promote_parser = review_subparsers.add_parser(
        "promote-claim-relation",
        help="Persist a reviewed claim-to-claim relation.",
    )
    review_promote_parser.add_argument("source_claim_id", help="Source claim ID.")
    review_promote_parser.add_argument("relation_type", choices=("supports", "refines", "contradicts"))
    review_promote_parser.add_argument("target_claim_id", help="Target claim ID.")
    review_promote_parser.add_argument("--confidence", type=float, default=1.0)
    review_promote_parser.add_argument("--reviewed-by", default="agent:review")
    review_promote_parser.add_argument("--note", help="Optional review note to persist in edge metadata.")
    review_promote_parser.set_defaults(handler=handle_review_promote_claim_relation)

    review_retract_parser = review_subparsers.add_parser(
        "retract-claim-relation",
        help="Retract a previously reviewed claim-to-claim relation.",
    )
    review_retract_parser.add_argument("source_claim_id", help="Source claim ID.")
    review_retract_parser.add_argument("relation_type", choices=("supports", "refines", "contradicts"))
    review_retract_parser.add_argument("target_claim_id", help="Target claim ID.")
    review_retract_parser.set_defaults(handler=handle_review_retract_claim_relation)

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

    output_parser = subparsers.add_parser("output", help="Generate direct research outputs from the local graph.")
    output_subparsers = output_parser.add_subparsers(dest="output_command", required=True)

    output_answer_parser = output_subparsers.add_parser("answer", help="Answer a research question from the local graph.")
    output_answer_parser.add_argument("question", help="Research question text.")
    output_answer_parser.set_defaults(handler=handle_output_answer)

    output_brief_parser = output_subparsers.add_parser("brief", help="Generate a structured topic briefing.")
    output_brief_parser.add_argument("topic", help="Topic text.")
    output_brief_parser.set_defaults(handler=handle_output_brief)

    output_disagreements_parser = output_subparsers.add_parser(
        "disagreements",
        help="Surface contradictions and refinements around a topic.",
    )
    output_disagreements_parser.add_argument("topic", help="Topic text.")
    output_disagreements_parser.set_defaults(handler=handle_output_disagreements)

    output_opportunities_parser = output_subparsers.add_parser(
        "opportunities",
        help="Generate research opportunities and next-step guidance for a topic.",
    )
    output_opportunities_parser.add_argument("topic", help="Topic text.")
    output_opportunities_parser.set_defaults(handler=handle_output_opportunities)

    output_reading_list_parser = output_subparsers.add_parser(
        "reading-list",
        help="Generate a prioritized reading path for a topic.",
    )
    output_reading_list_parser.add_argument("topic", help="Topic text.")
    output_reading_list_parser.set_defaults(handler=handle_output_reading_list)

    output_compare_parser = output_subparsers.add_parser(
        "compare",
        help="Compare two claims, papers, methods, datasets, or concepts.",
    )
    output_compare_parser.add_argument("left", help="Left target text or object ID.")
    output_compare_parser.add_argument("right", help="Right target text or object ID.")
    output_compare_parser.set_defaults(handler=handle_output_compare)

    output_open_questions_parser = output_subparsers.add_parser(
        "open-questions",
        help="Surface grounded open questions for a topic.",
    )
    output_open_questions_parser.add_argument("topic", help="Topic text.")
    output_open_questions_parser.set_defaults(handler=handle_output_open_questions)

    output_review_priorities_parser = output_subparsers.add_parser(
        "review-priorities",
        help="Surface review priorities and replication risks for a topic.",
    )
    output_review_priorities_parser.add_argument("topic", help="Topic text.")
    output_review_priorities_parser.set_defaults(handler=handle_output_review_priorities)

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


def handle_config_init(args: argparse.Namespace) -> int:
    del args
    destination = write_default_config(config_path())
    print(json.dumps({"config_path": str(destination)}, indent=2))
    return 0


def handle_config_show(args: argparse.Namespace) -> int:
    del args
    app_config = load_app_config()
    print(
        json.dumps(
            {
                "root": str(app_config.root),
                "data_dir": str(app_config.data_dir),
                "reference_pdf_acquisition": app_config.reference_pdf_acquisition,
                "llm": {
                    "base_url": app_config.llm_base_url,
                    "model": app_config.llm_model,
                    "api_key_env": app_config.llm_api_key_env,
                },
                "config_path": str(config_path(app_config.root)),
            },
            indent=2,
        )
    )
    return 0


def handle_skills_list(args: argparse.Namespace) -> int:
    del args
    payload = [
        {"name": skill.name, "description": skill.description}
        for skill in list_bundled_skills()
    ]
    print(json.dumps(payload, indent=2))
    return 0


def handle_skills_export(args: argparse.Namespace) -> int:
    payload = export_bundled_skills(args.destination)
    print(json.dumps(payload, indent=2))
    return 0


def handle_migrate(args: argparse.Namespace) -> int:
    del args
    paths = load_paths()
    conn = connect_db(paths.db_path)
    try:
        payload = apply_migrations(conn)
        initialize_db(conn)
        payload["current_version"] = current_schema_version(conn)
        print(json.dumps(payload, indent=2))
    finally:
        conn.close()
    return 0


def handle_ingest_pdf(args: argparse.Namespace) -> int:
    with _open_repository() as repo:
        paper = ingest_pdf(repo=repo, paths=load_paths(), pdf_path=args.path, title=args.title)
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_ingest_doi(args: argparse.Namespace) -> int:
    app_config = load_app_config()
    with _open_repository() as repo:
        paper = ingest_doi_reference(
            repo=repo,
            paths=load_paths(),
            doi=args.doi,
            provider=CrossrefMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_ingest_arxiv(args: argparse.Namespace) -> int:
    app_config = load_app_config()
    with _open_repository() as repo:
        paper = ingest_arxiv_reference(
            repo=repo,
            paths=load_paths(),
            arxiv_id=args.arxiv_id,
            provider=ArxivMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_batch_ingest(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest_path)
    results = []
    app_config = load_app_config()
    with _open_repository() as repo:
        for item in manifest:
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
            else:
                raise ValueError(f"Unsupported batch source type: {source_type}")
            results.append(_paper_to_payload(paper))
    print(json.dumps({"count": len(results), "papers": results}, indent=2))
    return 0


def handle_batch_extract(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest_path)
    results = []
    for item in manifest:
        paper_id = item["paper_id"] if isinstance(item, dict) else item
        mode = item.get("mode", args.mode) if isinstance(item, dict) else args.mode
        results.append(_run_batch_extract_item(args.stage, paper_id, mode))
    print(json.dumps({"stage": args.stage, "count": len(results), "results": results}, indent=2))
    return 0


def handle_show_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        paper = session.papers.get_paper(args.paper_id)
        artifacts = session.papers.get_artifacts_for_paper(args.paper_id)
        notes = session.notes.list_notes_for_target(target_id=args.paper_id, target_type="paper")
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
    print(json.dumps(payload, indent=2))
    return 0


def handle_note_add_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_paper_note(
            args.paper_id,
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


def handle_status_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        operations = _operations(session)
        payload = operations.paper_status(args.paper_id)
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
        if args.mode == "agent":
            task = session.tasks.create_task(
                task_type="summarize_paper",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=payload["artifact_id"],
                spec_version=payload["spec_version"],
                schema_version=payload["schema_version"],
            )
            payload["task_id"] = task.id
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


def handle_extract_text(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        paper = session.papers.get_paper(args.paper_id)
        payload = run_dual_track_mode(
            args.mode,
            heuristic=lambda: _artifact_payload(
                args.paper_id,
                args.mode,
                extract_text_for_paper(repo=session.papers, paths=paths, paper=paper),
            ),
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
            payload["task_id"] = task.id
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
            task = session.tasks.create_task(
                task_type="extract_claims",
                paper_id=args.paper_id,
                mode="agent",
                request_artifact_id=claims_payload["artifact_id"],
                spec_version=claims_payload["spec_version"],
                schema_version=claims_payload["schema_version"],
            )
            payload = {**claims_payload, "task_id": task.id}
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
    with _open_session() as session:
        artifact = import_text_result(
            repo=session.papers,
            paths=load_paths(),
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        session.tasks.complete_latest_task(args.paper_id, "extract_text", artifact.id)
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
        session.tasks.complete_latest_task(args.paper_id, "extract_claims", structured_claims_artifact)
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
    with _open_session() as session:
        payload = import_summary_result(
            repo=session.papers,
            paths=load_paths(),
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        session.tasks.complete_latest_task(args.paper_id, "summarize_paper", payload["artifact_id"])
    print(json.dumps(payload, indent=2))
    return 0


def handle_import_graph(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = import_graph_snapshot(session.papers.conn, args.json_path)
    print(json.dumps(payload, indent=2))
    return 0


def handle_export_graph(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = export_graph_snapshot(session.papers.conn, args.json_path)
    print(json.dumps(payload, indent=2))
    return 0


def handle_serve(args: argparse.Namespace) -> int:
    serve_http(args.host, args.port)
    return 0


def handle_tasks_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        tasks = session.tasks.list_tasks(paper_id=args.paper_id, status=args.status)
    print(json.dumps([_task_payload(task) for task in tasks], indent=2))
    return 0


def handle_tasks_show(args: argparse.Namespace) -> int:
    with _open_session() as session:
        task = session.tasks.get_task(args.task_id)
    print(json.dumps(_task_payload(task), indent=2))
    return 0


def handle_tasks_fail(args: argparse.Namespace) -> int:
    with _open_session() as session:
        task = session.tasks.fail_task(args.task_id, args.message)
    print(json.dumps(_task_payload(task), indent=2))
    return 0


def handle_review_promote_claim_relation(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).promote_claim_relation(
            source_claim_id=args.source_claim_id,
            relation_type=args.relation_type,
            target_claim_id=args.target_claim_id,
            confidence=args.confidence,
            reviewed_by=args.reviewed_by,
            note=args.note,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_retract_claim_relation(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).retract_claim_relation(
            source_claim_id=args.source_claim_id,
            relation_type=args.relation_type,
            target_claim_id=args.target_claim_id,
        )
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


def handle_output_answer(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).answer_question(args.question)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_brief(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_brief(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_disagreements(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_disagreements(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_opportunities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).research_opportunities(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_reading_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_reading_list(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_compare(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).compare_targets(args.left, args.right)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_open_questions(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_open_questions(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_review_priorities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_review_priorities(args.topic)
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
        notes: NoteRepository,
        edges: EdgeRepository,
        methods: MethodRepository,
        datasets: DatasetRepository,
        embeddings: EmbeddingRepository,
        tasks: TaskRepository,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings
        self.tasks = tasks


class _SessionContext:
    def __enter__(self) -> _Session:
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return _Session(
            papers=PaperRepository(self.conn),
            claims=ClaimRepository(self.conn),
            concepts=ConceptRepository(self.conn),
            notes=NoteRepository(self.conn),
            edges=EdgeRepository(self.conn),
            methods=MethodRepository(self.conn),
            datasets=DatasetRepository(self.conn),
            embeddings=EmbeddingRepository(self.conn),
            tasks=TaskRepository(self.conn),
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.conn.rollback()
        self.conn.close()


def _open_session() -> _SessionContext:
    return _SessionContext()


def _operations(session: _Session) -> ResearchOperations:
    return ResearchOperations(
        papers=session.papers,
        claims=session.claims,
        concepts=session.concepts,
        notes=session.notes,
        edges=session.edges,
        methods=session.methods,
        datasets=session.datasets,
        embeddings=session.embeddings,
        tasks=session.tasks,
    )


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
        "confidence": edge.confidence,
        "created_by": edge.created_by,
        "metadata": json.loads(edge.metadata_json or "{}"),
    }


def _note_payload(note) -> dict:
    return {
        "id": note.id,
        "target_id": note.target_id,
        "target_type": note.target_type,
        "content": note.content,
        "created_by": note.created_by,
        "created_at": note.created_at,
    }


def _task_payload(task) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "paper_id": task.paper_id,
        "mode": task.mode,
        "status": task.status,
        "request_artifact_id": task.request_artifact_id,
        "result_artifact_id": task.result_artifact_id,
        "spec_version": task.spec_version,
        "schema_version": task.schema_version,
        "error": json.loads(task.error_json) if task.error_json else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _load_manifest(manifest_path: Path):
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Batch manifest must be a JSON array.")
    return payload


def _resolve_manifest_path(manifest_path: Path, candidate: str) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def _run_batch_extract_item(stage: str, paper_id: str, mode: str) -> dict:
    with _open_session() as session:
        if stage == "text":
            paper = session.papers.get_paper(paper_id)
            if mode == "heuristic":
                artifact = extract_text_for_paper(session.papers, load_paths(), paper)
                return _artifact_payload(paper_id, mode, artifact)
            if mode == "llm-api":
                artifact = extract_text_with_llm(
                    repo=session.papers,
                    paths=load_paths(),
                    paper=paper,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _artifact_payload(paper_id, mode, artifact)
            request = create_text_request(session.papers, load_paths(), paper_id)
            task = session.tasks.create_task(
                "extract_text", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "claims":
            if mode == "heuristic":
                claims = extract_claims_for_paper(
                    load_paths(), session.papers, session.claims, session.concepts, session.edges, paper_id
                )
                return _claims_payload(paper_id, mode, claims)
            if mode == "llm-api":
                claims = extract_claims_with_llm(
                    load_paths(),
                    session.papers,
                    session.claims,
                    session.concepts,
                    session.edges,
                    paper_id,
                    OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _claims_payload(paper_id, mode, claims)
            request = create_claims_request(session.papers, load_paths(), paper_id)
            task = session.tasks.create_task(
                "extract_claims", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "methods":
            methods = extract_methods_for_paper(
                load_paths(),
                session.papers,
                session.claims,
                session.concepts,
                session.edges,
                session.methods,
                session.datasets,
                paper_id,
            )
            return {"paper_id": paper_id, "method_count": len(methods), "method_ids": [method.id for method in methods]}

        if stage == "datasets":
            datasets = extract_datasets_for_paper(
                load_paths(),
                session.papers,
                session.claims,
                session.edges,
                session.datasets,
                session.methods,
                paper_id,
            )
            return {"paper_id": paper_id, "dataset_count": len(datasets), "dataset_ids": [dataset.id for dataset in datasets]}

        if stage == "summary":
            if mode == "heuristic":
                return summarize_paper_heuristic(load_paths(), session.papers, session.claims, session.concepts, paper_id)
            if mode == "llm-api":
                return persist_summary_artifact(
                    session.papers,
                    load_paths(),
                    paper_id,
                    {
                        **OpenAICompatibleLlmProvider(load_llm_config()).summarize_paper(
                            build_summary_input(session.papers, session.claims, session.concepts, paper_id)
                        ),
                        "mode": "llm-api",
                    },
                    "paper_summary",
                    "paper_summary.json",
                )
            request = create_summary_request(
                session.papers, session.claims, session.concepts, load_paths(), paper_id
            )
            task = session.tasks.create_task(
                "summarize_paper", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            return {**request, "mode": "agent", "task_id": task.id}

    raise ValueError(f"Unsupported batch stage: {stage}")


def _artifact_id_for_type(repo: PaperRepository, paper_id: str, artifact_type: str) -> str | None:
    for artifact in repo.get_artifacts_for_paper(paper_id):
        if artifact.artifact_type == artifact_type:
            return artifact.id
    return None
