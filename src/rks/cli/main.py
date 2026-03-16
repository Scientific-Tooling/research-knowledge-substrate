from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks import __version__
from rks.agent import (
    create_claims_request,
    create_summary_request,
    create_text_request,
    import_claims_result,
    import_summary_result,
    import_text_result,
    record_task_report,
)
from rks.agent_skills import SKILL_BUNDLE_VERSION, export_bundled_skills, list_bundled_skills
from rks.config import config_path, load_app_config, load_llm_config, load_paths, write_default_config
from rks.extraction import (
    extract_claims_for_paper,
    extract_claims_with_llm,
    extract_datasets_for_paper,
    extract_methods_for_paper,
    extract_text_for_paper,
    extract_text_with_llm,
)
from rks.ingestion import (
    ingest_arxiv_reference,
    ingest_doi_reference,
    ingest_pdf,
    ingest_pmid_reference,
    ingest_url_reference,
)
from rks.llm import ALL_EXTRACTION_MODES, run_dual_track_mode
from rks.operations import ResearchOperations
from rks.providers import (
    ArxivMetadataProvider,
    CrossrefMetadataProvider,
    LocalHashEmbeddingProvider,
    OpenAICompatibleLlmProvider,
    PubmedMetadataProvider,
)
from rks.query import QueryService, index_embeddings
from rks.reasoning import summarize_paper_heuristic
from rks.reasoning.summary import build_summary_input, persist_summary_artifact
from rks.storage import (
    CandidateRepository,
    ClaimRepository,
    ConceptRepository,
    ConflictClusterRepository,
    DatasetRepository,
    EmbeddingRepository,
    EdgeRepository,
    EvolutionRepository,
    HypothesisRepository,
    MethodRepository,
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    TaskRepository,
    connect_db,
    export_graph_snapshot,
    import_graph_snapshot,
    initialize_db,
)
from rks.storage.db import apply_migrations, current_schema_version, list_migration_files
from rks.service import serve_http


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Initialize the local RKS SQLite database.")
    init_parser.set_defaults(handler=handle_init_db)

    doctor_parser = subparsers.add_parser("doctor", help="Run installation and environment self-checks.")
    doctor_parser.set_defaults(handler=handle_doctor)

    extraction_quality_parser = subparsers.add_parser(
        "extraction-quality", help="Show extraction quality metrics across all papers."
    )
    extraction_quality_parser.set_defaults(handler=handle_extraction_quality)

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

    ingest_pmid_parser = ingest_subparsers.add_parser("pmid", help="Ingest a PubMed reference by PMID.")
    ingest_pmid_parser.add_argument("pmid", help="PubMed identifier, for example 31452104.")
    ingest_pmid_parser.set_defaults(handler=handle_ingest_pmid)

    ingest_url_parser = ingest_subparsers.add_parser(
        "url",
        help="Ingest a paper from a canonical reference URL or direct PDF URL.",
    )
    ingest_url_parser.add_argument("url", help="DOI, arXiv, PubMed, or direct PDF URL.")
    ingest_url_parser.set_defaults(handler=handle_ingest_url)

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
        help="Execute the missing local heuristic steps instead of only planning them.",
    )
    prepare_paper_output_parser.set_defaults(handler=handle_prepare_paper_output)

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

    project_parser = subparsers.add_parser("project", help="Create and organize research projects.")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)

    project_create_parser = project_subparsers.add_parser("create", help="Create a research project.")
    project_create_parser.add_argument("--name", required=True, help="Project name.")
    project_create_parser.add_argument("--description", help="Optional project description.")
    project_create_parser.add_argument("--research-question", help="Optional core research question.")
    project_create_parser.add_argument("--status", default="active", help="Project status label.")
    project_create_parser.add_argument("--created-by", default="human:user", help="Project creator label.")
    project_create_parser.set_defaults(handler=handle_project_create)

    project_list_parser = project_subparsers.add_parser("list", help="List research projects.")
    project_list_parser.set_defaults(handler=handle_project_list)

    project_add_paper_parser = project_subparsers.add_parser("add-paper", help="Link a paper to a project.")
    project_add_paper_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_add_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    project_add_paper_parser.add_argument("--link-type", default="in_scope", help="Project-paper link label.")
    project_add_paper_parser.add_argument("--created-by", default="human:user", help="Actor label for the link.")
    project_add_paper_parser.set_defaults(handler=handle_project_add_paper)

    project_papers_parser = project_subparsers.add_parser("papers", help="List papers linked to a project.")
    project_papers_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_papers_parser.set_defaults(handler=handle_project_papers)

    project_add_link_parser = project_subparsers.add_parser("add-link", help="Link a graph object to a project.")
    project_add_link_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_add_link_parser.add_argument("object_type", choices=("paper", "claim", "method", "dataset", "concept"))
    project_add_link_parser.add_argument("object_id", help="Target object ID.")
    project_add_link_parser.add_argument("--link-type", default="in_scope", help="Project link label.")
    project_add_link_parser.add_argument("--created-by", default="human:user", help="Actor label for the link.")
    project_add_link_parser.set_defaults(handler=handle_project_add_link)

    project_links_parser = project_subparsers.add_parser("links", help="List graph objects linked to a project.")
    project_links_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_links_parser.add_argument("--object-type", choices=("paper", "claim", "method", "dataset", "concept"))
    project_links_parser.set_defaults(handler=handle_project_links)

    hypothesis_parser = subparsers.add_parser("hypothesis", help="Create and inspect project hypotheses.")
    hypothesis_subparsers = hypothesis_parser.add_subparsers(dest="hypothesis_command", required=True)

    hypothesis_create_parser = hypothesis_subparsers.add_parser("create", help="Create a hypothesis for a project.")
    hypothesis_create_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    hypothesis_create_parser.add_argument("--text", required=True, help="Hypothesis text.")
    hypothesis_create_parser.add_argument("--status", default="draft", help="Hypothesis status label.")
    hypothesis_create_parser.add_argument("--confidence", type=float, help="Optional confidence score.")
    hypothesis_create_parser.add_argument("--context", help="Optional JSON object describing hypothesis context.")
    hypothesis_create_parser.add_argument("--created-by", default="human:user", help="Hypothesis author label.")
    hypothesis_create_parser.set_defaults(handler=handle_hypothesis_create)

    hypothesis_list_parser = hypothesis_subparsers.add_parser("list", help="List hypotheses for a project.")
    hypothesis_list_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    hypothesis_list_parser.set_defaults(handler=handle_hypothesis_list)

    hypothesis_add_evidence_parser = hypothesis_subparsers.add_parser(
        "add-evidence",
        help="Link a paper or claim as evidence for a hypothesis.",
    )
    hypothesis_add_evidence_parser.add_argument("hypothesis_id", help="Hypothesis ID, for example h_000001.")
    hypothesis_add_evidence_parser.add_argument("object_type", choices=("paper", "claim"))
    hypothesis_add_evidence_parser.add_argument("object_id", help="Target object ID.")
    hypothesis_add_evidence_parser.add_argument("--relation-type", default="supported_by", help="Evidence relation label.")
    hypothesis_add_evidence_parser.add_argument("--note", help="Optional note stored on the evidence link.")
    hypothesis_add_evidence_parser.add_argument("--created-by", default="human:user", help="Actor label for the evidence link.")
    hypothesis_add_evidence_parser.set_defaults(handler=handle_hypothesis_add_evidence)

    hypothesis_evidence_parser = hypothesis_subparsers.add_parser("evidence", help="List evidence linked to a hypothesis.")
    hypothesis_evidence_parser.add_argument("hypothesis_id", help="Hypothesis ID, for example h_000001.")
    hypothesis_evidence_parser.set_defaults(handler=handle_hypothesis_evidence)

    note_parser = subparsers.add_parser("note", help="Add or inspect user and agent notes.")
    note_subparsers = note_parser.add_subparsers(dest="note_command", required=True)

    note_add_parser = note_subparsers.add_parser("add", help="Add a note to a stored object.")
    note_add_subparsers = note_add_parser.add_subparsers(dest="note_target", required=True)
    note_add_paper_parser = note_add_subparsers.add_parser("paper", help="Add a note to a paper.")
    note_add_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    note_add_paper_parser.add_argument("--content", required=True, help="Note text to store.")
    note_add_paper_parser.add_argument("--created-by", default="human:user", help="Note author label.")
    note_add_paper_parser.set_defaults(handler=handle_note_add_paper)
    note_add_project_parser = note_add_subparsers.add_parser("project", help="Add a note to a project.")
    note_add_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    note_add_project_parser.add_argument("--content", required=True, help="Note text to store.")
    note_add_project_parser.add_argument("--created-by", default="human:user", help="Note author label.")
    note_add_project_parser.set_defaults(handler=handle_note_add_project)

    note_list_parser = note_subparsers.add_parser("list", help="List notes for a stored object.")
    note_list_subparsers = note_list_parser.add_subparsers(dest="note_target", required=True)
    note_list_paper_parser = note_list_subparsers.add_parser("paper", help="List notes for a paper.")
    note_list_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    note_list_paper_parser.set_defaults(handler=handle_note_list_paper)
    note_list_project_parser = note_list_subparsers.add_parser("project", help="List notes for a project.")
    note_list_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    note_list_project_parser.set_defaults(handler=handle_note_list_project)

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

    review_materialize_parser = review_subparsers.add_parser(
        "materialize-candidates",
        help="Materialize inferred claim relations into the candidate table.",
    )
    review_materialize_parser.add_argument("--claim-id", default=None, help="Optional claim ID to scope materialization.")
    review_materialize_parser.set_defaults(handler=handle_review_materialize_candidates)

    review_candidates_parser = review_subparsers.add_parser(
        "list-candidates",
        help="List claim relation candidates.",
    )
    review_candidates_parser.add_argument("--claim-id", default=None, help="Optional claim ID to filter.")
    review_candidates_parser.add_argument("--status", default=None, choices=("pending", "promoted", "rejected", "superseded"))
    review_candidates_parser.set_defaults(handler=handle_review_list_candidates)

    review_promote_candidate_parser = review_subparsers.add_parser(
        "promote-candidate",
        help="Promote a candidate relation into the durable graph.",
    )
    review_promote_candidate_parser.add_argument("candidate_id", help="Candidate ID.")
    review_promote_candidate_parser.add_argument("--reviewed-by", default="agent:review")
    review_promote_candidate_parser.set_defaults(handler=handle_review_promote_candidate)

    review_reject_candidate_parser = review_subparsers.add_parser(
        "reject-candidate",
        help="Reject a candidate relation.",
    )
    review_reject_candidate_parser.add_argument("candidate_id", help="Candidate ID.")
    review_reject_candidate_parser.set_defaults(handler=handle_review_reject_candidate)

    # Evolution subcommands
    evolution_parser = subparsers.add_parser("evolution", help="Knowledge evolution events and timeline.")
    evolution_subparsers = evolution_parser.add_subparsers(dest="evolution_command", required=True)

    evo_events_parser = evolution_subparsers.add_parser("events", help="List evolution events for a subject.")
    evo_events_parser.add_argument("subject_id", help="Subject ID (claim, concept, hypothesis).")
    evo_events_parser.add_argument("--type", dest="subject_type", default=None, help="Optional subject type filter.")
    evo_events_parser.set_defaults(handler=handle_evolution_events)

    evo_snapshot_parser = evolution_subparsers.add_parser(
        "snapshot-concept", help="Take a timeline snapshot of a concept."
    )
    evo_snapshot_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_snapshot_parser.set_defaults(handler=handle_evolution_snapshot_concept)

    evo_timeline_parser = evolution_subparsers.add_parser(
        "concept-timeline", help="Show the full timeline for a concept."
    )
    evo_timeline_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_timeline_parser.set_defaults(handler=handle_evolution_concept_timeline)

    evo_hypothesis_parser = evolution_subparsers.add_parser(
        "hypothesis", help="Show evolution view for a hypothesis."
    )
    evo_hypothesis_parser.add_argument("hypothesis_id", help="Hypothesis ID.")
    evo_hypothesis_parser.set_defaults(handler=handle_evolution_hypothesis)

    evo_bucketed_parser = evolution_subparsers.add_parser(
        "build-timeline-bucketed", help="Build time-bucketed timeline snapshots for a concept."
    )
    evo_bucketed_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_bucketed_parser.add_argument("--bucket-size", default="yearly", choices=("yearly",), help="Bucket size.")
    evo_bucketed_parser.set_defaults(handler=handle_evolution_build_timeline_bucketed)

    evo_cluster_parser = evolution_subparsers.add_parser(
        "cluster-conflicts", help="Detect and persist conflict clusters from contradicts edges."
    )
    evo_cluster_parser.add_argument("--concept-id", default=None, help="Optional concept ID to scope clustering.")
    evo_cluster_parser.set_defaults(handler=handle_evolution_cluster_conflicts)

    evo_list_clusters_parser = evolution_subparsers.add_parser(
        "list-clusters", help="List conflict clusters for a concept."
    )
    evo_list_clusters_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_list_clusters_parser.set_defaults(handler=handle_evolution_list_clusters)

    evo_project_parser = evolution_subparsers.add_parser(
        "project-summary", help="Show evolution summary for a project."
    )
    evo_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    evo_project_parser.set_defaults(handler=handle_evolution_project_summary)

    evo_conflict_graph_parser = evolution_subparsers.add_parser(
        "conflict-graph", help="Show the full contradiction graph for a concept (nodes + edges)."
    )
    evo_conflict_graph_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_conflict_graph_parser.set_defaults(handler=handle_evolution_conflict_graph)

    evo_hypothesis_bucketed_parser = evolution_subparsers.add_parser(
        "hypothesis-bucketed", help="Show time-bucketed evolution view for a hypothesis."
    )
    evo_hypothesis_bucketed_parser.add_argument("hypothesis_id", help="Hypothesis ID.")
    evo_hypothesis_bucketed_parser.add_argument("--bucket-size", default="yearly", choices=("yearly",), help="Bucket size.")
    evo_hypothesis_bucketed_parser.set_defaults(handler=handle_evolution_hypothesis_bucketed)

    evo_project_timeline_parser = evolution_subparsers.add_parser(
        "project-timeline", help="Show aggregate year-by-year evidence timeline for a project."
    )
    evo_project_timeline_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    evo_project_timeline_parser.set_defaults(handler=handle_evolution_project_timeline)

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

    output_project_answer_parser = output_subparsers.add_parser(
        "project-answer",
        help="Answer a project-scoped research question from project-linked evidence.",
    )
    output_project_answer_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_answer_parser.add_argument("--question", help="Optional override question text.")
    output_project_answer_parser.set_defaults(handler=handle_output_project_answer)

    output_project_brief_parser = output_subparsers.add_parser(
        "project-brief",
        help="Generate a structured project briefing from project-linked evidence.",
    )
    output_project_brief_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_brief_parser.set_defaults(handler=handle_output_project_brief)

    output_project_disagreements_parser = output_subparsers.add_parser(
        "project-disagreements",
        help="Surface contradictions and refinements within a project scope.",
    )
    output_project_disagreements_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_disagreements_parser.set_defaults(handler=handle_output_project_disagreements)

    output_project_opportunities_parser = output_subparsers.add_parser(
        "project-opportunities",
        help="Generate research opportunities within a project scope.",
    )
    output_project_opportunities_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_opportunities_parser.set_defaults(handler=handle_output_project_opportunities)

    output_project_reading_list_parser = output_subparsers.add_parser(
        "project-reading-list",
        help="Generate a prioritized project reading path.",
    )
    output_project_reading_list_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_reading_list_parser.set_defaults(handler=handle_output_project_reading_list)

    output_project_open_questions_parser = output_subparsers.add_parser(
        "project-open-questions",
        help="Surface grounded open questions within a project scope.",
    )
    output_project_open_questions_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_open_questions_parser.set_defaults(handler=handle_output_project_open_questions)

    output_project_review_priorities_parser = output_subparsers.add_parser(
        "project-review-priorities",
        help="Surface project-scoped review priorities and replication risks.",
    )
    output_project_review_priorities_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_review_priorities_parser.set_defaults(handler=handle_output_project_review_priorities)

    plan_parser = subparsers.add_parser("plan", help="Generate deterministic research workflow plans.")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)

    plan_query_parser = plan_subparsers.add_parser("query", help="Plan the next RKS commands for a research request.")
    plan_query_parser.add_argument("request", help="Research request text.")
    plan_query_parser.add_argument("--project-id", help="Optional project scope to plan against.")
    plan_query_parser.set_defaults(handler=handle_plan_query)

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


def handle_doctor(args: argparse.Namespace) -> int:
    del args
    app_config = load_app_config()
    paths = load_paths()
    config_exists = config_path(app_config.root).exists()
    data_dir_exists = paths.data_dir.exists()
    db_exists = paths.db_path.exists()
    checks = {
        "config_file": {
            "ok": config_exists,
            "path": str(config_path(app_config.root)),
        },
        "data_dir": {
            "ok": data_dir_exists,
            "path": str(paths.data_dir),
        },
        "database": {
            "ok": db_exists,
            "path": str(paths.db_path),
        },
        "migrations": {
            "ok": True,
            "count": len(list_migration_files()),
        },
        "bundled_skills": {
            "ok": True,
            "bundle_version": SKILL_BUNDLE_VERSION,
            "skill_count": len(list_bundled_skills()),
        },
    }
    overall_status = "ok" if all(item["ok"] for item in checks.values()) else "action_required"
    payload = {
        "version": __version__,
        "overall_status": overall_status,
        "paths": {
            "root": str(app_config.root),
            "data_dir": str(paths.data_dir),
            "db_path": str(paths.db_path),
        },
        "checks": checks,
        "recommended_actions": _doctor_recommended_actions(checks),
    }
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


def _doctor_recommended_actions(checks: dict) -> list[str]:
    actions = []
    if not checks["config_file"]["ok"]:
        actions.append("rks config init")
    if not checks["database"]["ok"]:
        actions.append("rks init-db")
    if not checks["data_dir"]["ok"] and "rks init-db" not in actions:
        actions.append("rks init-db")
    if not actions:
        actions.append("rks --help")
    return actions


def handle_extraction_quality(args: argparse.Namespace) -> int:
    del args
    with _open_session() as session:
        payload = _operations(session).extraction_quality_report()
    print(json.dumps(payload, indent=2))
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


def handle_ingest_pmid(args: argparse.Namespace) -> int:
    app_config = load_app_config()
    with _open_repository() as repo:
        paper = ingest_pmid_reference(
            repo=repo,
            paths=load_paths(),
            pmid=args.pmid,
            provider=PubmedMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


def handle_ingest_url(args: argparse.Namespace) -> int:
    app_config = load_app_config()
    with _open_repository() as repo:
        paper = ingest_url_reference(
            repo=repo,
            paths=load_paths(),
            url=args.url,
            crossref_provider=CrossrefMetadataProvider(),
            arxiv_provider=ArxivMetadataProvider(),
            pubmed_provider=PubmedMetadataProvider(),
            acquire_pdf=app_config.reference_pdf_acquisition == "auto",
        )
    print(json.dumps(_paper_to_payload(paper), indent=2))
    return 0


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
    return 0


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
    return 0


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
    return 0


def handle_prepare_paper_output(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).prepare_paper_for_output(args.paper_id, apply=args.apply)
    print(json.dumps(payload, indent=2))
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


def handle_project_create(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).create_project(
            name=args.name,
            description=args.description,
            research_question=args.research_question,
            status=args.status,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_projects()
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_add_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_project_paper(
            args.project_id,
            args.paper_id,
            link_type=args.link_type,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_papers(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_papers(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_add_link(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_project_link(
            args.project_id,
            args.object_type,
            args.object_id,
            link_type=args.link_type,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_links(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_links(args.project_id, object_type=args.object_type)
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_create(args: argparse.Namespace) -> int:
    context = json.loads(args.context) if args.context else None
    with _open_session() as session:
        payload = _operations(session).create_hypothesis(
            args.project_id,
            text=args.text,
            status=args.status,
            confidence=args.confidence,
            context=context,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_hypotheses(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_add_evidence(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_hypothesis_evidence(
            args.hypothesis_id,
            args.object_type,
            args.object_id,
            relation_type=args.relation_type,
            note=args.note,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_evidence(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_hypothesis_evidence(args.hypothesis_id)
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


def handle_note_add_project(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_project_note(
            args.project_id,
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


def handle_note_list_project(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_notes(args.project_id)
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
            record_task_report(session.papers, load_paths(), task, note="Queued from rks summarize paper --mode agent.")
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
            record_task_report(session.papers, load_paths(), task, note="Queued from rks extract text --mode agent.")
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
            record_task_report(session.papers, load_paths(), task, note="Queued from rks extract claims --mode agent.")
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
        record_task_report(session.papers, load_paths(), task, note="Task marked as failed.", error={"message": args.message})
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


def handle_review_materialize_candidates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).materialize_claim_relation_candidates(
            claim_id=args.claim_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_list_candidates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_relation_candidates(
            claim_id=args.claim_id,
            status=args.status,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_promote_candidate(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).promote_candidate(
            candidate_id=args.candidate_id,
            reviewed_by=args.reviewed_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_reject_candidate(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).reject_candidate(
            candidate_id=args.candidate_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_events(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_evolution_events(
            subject_id=args.subject_id,
            subject_type=args.subject_type,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_snapshot_concept(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_concept_timeline(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_concept_timeline(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).concept_timeline(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_hypothesis(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_hypothesis_evolution(
            hypothesis_id=args.hypothesis_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_build_timeline_bucketed(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_concept_timeline_bucketed(
            concept_id=args.concept_id,
            bucket_size=args.bucket_size,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_cluster_conflicts(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).cluster_claim_conflicts(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_list_clusters(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_conflict_clusters(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_project_summary(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_evolution_summary(
            project_id=args.project_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_conflict_graph(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).conflict_graph(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_hypothesis_bucketed(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_hypothesis_evolution_bucketed(
            hypothesis_id=args.hypothesis_id,
            bucket_size=args.bucket_size,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_project_timeline(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_evolution_timeline(
            project_id=args.project_id,
        )
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


def handle_output_project_answer(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_answer(args.project_id, question=args.question)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_brief(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_brief(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_disagreements(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_disagreements(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_opportunities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_opportunities(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_reading_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_reading_list(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_open_questions(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_open_questions(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_review_priorities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_review_priorities(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_plan_query(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).plan_query(args.request, project_id=args.project_id)
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
        projects: ProjectRepository,
        hypotheses: HypothesisRepository,
        claims: ClaimRepository,
        concepts: ConceptRepository,
        notes: NoteRepository,
        edges: EdgeRepository,
        methods: MethodRepository,
        datasets: DatasetRepository,
        embeddings: EmbeddingRepository,
        tasks: TaskRepository,
        candidates: CandidateRepository | None = None,
        evolution: EvolutionRepository | None = None,
        conflict_clusters: ConflictClusterRepository | None = None,
    ):
        self.papers = papers
        self.projects = projects
        self.hypotheses = hypotheses
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings
        self.tasks = tasks
        self.candidates = candidates
        self.evolution = evolution
        self.conflict_clusters = conflict_clusters


class _SessionContext:
    def __enter__(self) -> _Session:
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return _Session(
            papers=PaperRepository(self.conn),
            projects=ProjectRepository(self.conn),
            hypotheses=HypothesisRepository(self.conn),
            claims=ClaimRepository(self.conn),
            concepts=ConceptRepository(self.conn),
            notes=NoteRepository(self.conn),
            edges=EdgeRepository(self.conn),
            methods=MethodRepository(self.conn),
            datasets=DatasetRepository(self.conn),
            embeddings=EmbeddingRepository(self.conn),
            tasks=TaskRepository(self.conn),
            candidates=CandidateRepository(self.conn),
            evolution=EvolutionRepository(self.conn),
            conflict_clusters=ConflictClusterRepository(self.conn),
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
        projects=session.projects,
        hypotheses=session.hypotheses,
        claims=session.claims,
        concepts=session.concepts,
        notes=session.notes,
        edges=session.edges,
        methods=session.methods,
        datasets=session.datasets,
        embeddings=session.embeddings,
        tasks=session.tasks,
        candidates=session.candidates,
        evolution=session.evolution,
        conflict_clusters=session.conflict_clusters,
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


def _project_to_payload(project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "research_question": project.research_question,
        "status": project.status,
        "created_by": project.created_by,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
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
            record_task_report(session.papers, load_paths(), task, note="Queued from rks batch extract text --mode agent.")
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
            record_task_report(session.papers, load_paths(), task, note="Queued from rks batch extract claims --mode agent.")
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
            record_task_report(session.papers, load_paths(), task, note="Queued from rks batch extract summary --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

    raise ValueError(f"Unsupported batch stage: {stage}")


def _run_batch_output_item(surface: str, item) -> dict:
    with _open_session() as session:
        operations = _operations(session)
        if surface == "answer":
            question = item["question"] if isinstance(item, dict) else str(item)
            payload = operations.answer_question(question)
            return {"surface": surface, "question": question, "payload": payload}
        if surface == "brief":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_brief(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "disagreements":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_disagreements(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "opportunities":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.research_opportunities(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "reading-list":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_reading_list(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "open-questions":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_open_questions(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "review-priorities":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_review_priorities(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "compare":
            if not isinstance(item, dict) or "left" not in item or "right" not in item:
                raise ValueError("Batch compare items must be objects with `left` and `right`.")
            payload = operations.compare_targets(item["left"], item["right"])
            return {"surface": surface, "left": item["left"], "right": item["right"], "payload": payload}
    raise ValueError(f"Unsupported batch output surface: {surface}")


def _batch_ingest_audit(results: list[dict], failures: list[dict]) -> dict:
    source_type_counts = {}
    source_pdf_available = 0
    for paper in results:
        source_type_counts[paper["source_type"]] = source_type_counts.get(paper["source_type"], 0) + 1
        if paper.get("pdf_path"):
            source_pdf_available += 1
    return {
        "success_count": len(results),
        "failure_count": len(failures),
        "source_pdf_available_count": source_pdf_available,
        "source_type_counts": source_type_counts,
    }


def _batch_extract_audit(stage: str, results: list[dict], failures: list[dict]) -> dict:
    audit = {
        "stage": stage,
        "success_count": len(results),
        "failure_count": len(failures),
        "queued_task_count": sum(1 for result in results if result.get("mode") == "agent" and result.get("task_id")),
    }
    if stage == "claims":
        audit["total_claim_count"] = sum(result.get("claim_count", 0) for result in results)
    elif stage == "methods":
        audit["total_method_count"] = sum(result.get("method_count", 0) for result in results)
    elif stage == "datasets":
        audit["total_dataset_count"] = sum(result.get("dataset_count", 0) for result in results)
    elif stage == "summary":
        audit["summary_artifact_count"] = sum(1 for result in results if result.get("artifact_id"))
    elif stage == "text":
        audit["text_artifact_count"] = sum(1 for result in results if result.get("artifact_id"))
    return audit


def _batch_output_audit(surface: str, results: list[dict], failures: list[dict]) -> dict:
    payload_key = {
        "answer": "question",
        "brief": "topic",
        "disagreements": "topic",
        "opportunities": "topic",
        "reading-list": "topic",
        "open-questions": "topic",
        "review-priorities": "topic",
        "compare": "left",
    }[surface]
    return {
        "surface": surface,
        "success_count": len(results),
        "failure_count": len(failures),
        "items": [result[payload_key] for result in results if payload_key in result],
    }


def _artifact_id_for_type(repo: PaperRepository, paper_id: str, artifact_type: str) -> str | None:
    for artifact in repo.get_artifacts_for_paper(paper_id):
        if artifact.artifact_type == artifact_type:
            return artifact.id
    return None
