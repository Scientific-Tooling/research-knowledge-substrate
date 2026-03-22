from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rks import __version__
from rks.agent import (
    create_claims_request,
    create_datasets_request,
    create_extract_all_request,
    create_methods_request,
    create_summary_request,
    create_text_request,
    import_claims_result,
    import_datasets_result,
    import_extract_all_result,
    import_methods_result,
    import_summary_result,
    import_text_result,
    record_task_report,
)
from rks.agent_skills import SKILL_BUNDLE_VERSION, export_bundled_skills, list_bundled_skills
from rks.config import (
    ALL_AUTO_EXTRACT_MODES,
    ConfigError,
    global_config_path,
    load_app_config,
    load_global_config,
    load_llm_config,
    load_paths,
    write_global_config,
)
from rks.extraction import (
    extract_all_with_llm,
    extract_claims_with_llm,
    extract_datasets_with_llm,
    extract_methods_with_llm,
    extract_text_with_llm,
)
from rks.ingestion import (
    ingest_arxiv_reference,
    ingest_doi_reference,
    ingest_pdf,
    ingest_pmid_reference,
    ingest_url_reference,
)
from rks.ingestion.pipeline import run_post_ingest_pipeline
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
from rks.storage.workspace import export_workspace, import_workspace
from rks.service import serve_http


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Set the global RKS data directory and initialize the database.")
    init_parser.add_argument("path", type=Path, help="Directory to store RKS data (PDFs, database, artifacts).")
    init_parser.set_defaults(handler=handle_init)

    init_db_parser = subparsers.add_parser("init-db", help="Initialize the RKS SQLite database (requires prior `rks init`).")
    init_db_parser.set_defaults(handler=handle_init_db)

    clear_parser = subparsers.add_parser("clear", help="Delete all papers, artifacts, and the database. Keeps global config.")
    clear_parser.add_argument("--yes", action="store_true", help="Confirm deletion. Required to actually clear data.")
    clear_parser.set_defaults(handler=handle_clear)

    doctor_parser = subparsers.add_parser("doctor", help="Run installation and environment self-checks.")
    doctor_parser.set_defaults(handler=handle_doctor)

    extraction_quality_parser = subparsers.add_parser(
        "extraction-quality", help="Show extraction quality metrics across all papers."
    )
    extraction_quality_parser.set_defaults(handler=handle_extraction_quality)

    stats_parser = subparsers.add_parser("stats", help="Show workspace counts and storage coverage metrics.")
    stats_parser.set_defaults(handler=handle_stats)

    evaluate_parser = subparsers.add_parser("evaluate", help="Run quality baseline checks.")
    evaluate_subparsers = evaluate_parser.add_subparsers(dest="evaluate_command", required=True)

    evaluate_baseline_parser = evaluate_subparsers.add_parser(
        "baseline",
        help="Evaluate extraction quality metrics against a baseline spec JSON.",
    )
    evaluate_baseline_parser.add_argument("spec_path", type=Path, help="Path to a baseline spec JSON file.")
    evaluate_baseline_parser.set_defaults(handler=handle_evaluate_baseline)

    config_parser = subparsers.add_parser("config", help="Manage RKS configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_show_parser = config_subparsers.add_parser("show", help="Show the effective configuration and global config path.")
    config_show_parser.set_defaults(handler=handle_config_show)

    config_set_parser = config_subparsers.add_parser("set", help="Set a configuration value in the global config.")
    config_set_subparsers = config_set_parser.add_subparsers(dest="config_set_key", required=True)

    config_set_data_dir_parser = config_set_subparsers.add_parser("data-dir", help="Set the global data directory path.")
    config_set_data_dir_parser.add_argument("path", type=Path, help="Absolute or relative path to the data directory.")
    config_set_data_dir_parser.set_defaults(handler=handle_config_set_data_dir)

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

    papers_parser = subparsers.add_parser("papers", help="List and manage tracked papers.")
    papers_subparsers = papers_parser.add_subparsers(dest="papers_command", required=True)

    papers_list_parser = papers_subparsers.add_parser("list", help="List tracked papers.")
    papers_list_parser.add_argument("--limit", type=int, default=20, help="Maximum papers to return.")
    papers_list_parser.add_argument("--offset", type=int, default=0, help="Offset for pagination.")
    papers_list_parser.add_argument(
        "--sort",
        choices=("created_at", "updated_at"),
        default="created_at",
        help="Sort field for returned papers.",
    )
    papers_list_parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Sort direction.",
    )
    papers_list_parser.add_argument(
        "--tag",
        help="Optional tag filter (for example read_later).",
    )
    papers_list_parser.set_defaults(handler=handle_papers_list)

    papers_mark_parser = papers_subparsers.add_parser("mark", help="Add a tag to a paper.")
    papers_mark_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    papers_mark_parser.add_argument(
        "--tag",
        default="read_later",
        help="Tag to add (for example read_later, survey, replication).",
    )
    papers_mark_parser.set_defaults(handler=handle_papers_mark)

    papers_unmark_parser = papers_subparsers.add_parser("unmark", help="Remove a tag from a paper.")
    papers_unmark_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    papers_unmark_parser.add_argument(
        "--tag",
        required=True,
        help="Tag to remove.",
    )
    papers_unmark_parser.set_defaults(handler=handle_papers_unmark)

    papers_tags_parser = papers_subparsers.add_parser("tags", help="List tags for a paper.")
    papers_tags_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    papers_tags_parser.set_defaults(handler=handle_papers_tags)

    papers_read_later_parser = papers_subparsers.add_parser("read-later", help="List papers marked as read_later.")
    papers_read_later_parser.add_argument("--limit", type=int, default=20, help="Maximum papers to return.")
    papers_read_later_parser.add_argument("--offset", type=int, default=0, help="Offset for pagination.")
    papers_read_later_parser.add_argument(
        "--sort",
        choices=("created_at", "updated_at"),
        default="created_at",
        help="Sort field for returned papers.",
    )
    papers_read_later_parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Sort direction.",
    )
    papers_read_later_parser.set_defaults(handler=handle_papers_read_later)

    papers_find_duplicates_parser = papers_subparsers.add_parser(
        "find-duplicates",
        help="Find likely duplicate papers by identifier and optional title matching.",
    )
    papers_find_duplicates_parser.add_argument(
        "--mode",
        choices=("title", "identifiers"),
        default="title",
        help="Detection mode. title uses DOI/arXiv/title; identifiers uses DOI/arXiv only.",
    )
    papers_find_duplicates_parser.set_defaults(handler=handle_papers_find_duplicates)

    papers_merge_parser = papers_subparsers.add_parser(
        "merge",
        help="Merge a duplicate paper into a target paper and delete the source paper.",
    )
    papers_merge_parser.add_argument("target_paper_id", help="Canonical paper ID to keep, for example p_000001.")
    papers_merge_parser.add_argument("source_paper_id", help="Duplicate paper ID to merge and remove.")
    papers_merge_parser.add_argument(
        "--prefer",
        choices=("target", "source"),
        default="target",
        help="When both papers have the same field or artifact type, prefer target or source.",
    )
    papers_merge_parser.set_defaults(handler=handle_papers_merge)

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

    import_methods_parser = import_subparsers.add_parser("methods", help="Import extracted methods JSON for a paper.")
    import_methods_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_methods_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_methods_parser.set_defaults(handler=handle_import_methods)

    import_datasets_parser = import_subparsers.add_parser("datasets", help="Import extracted datasets JSON for a paper.")
    import_datasets_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_datasets_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_datasets_parser.set_defaults(handler=handle_import_datasets)

    import_summary_parser = import_subparsers.add_parser("summary", help="Import a paper summary JSON for a paper.")
    import_summary_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_summary_parser.add_argument("json_path", type=Path, help="Path to a JSON file produced by an agent.")
    import_summary_parser.set_defaults(handler=handle_import_summary)

    import_all_parser = import_subparsers.add_parser(
        "all", help="Import a combined paper.v1 extraction result (text+claims+methods+datasets+summary)."
    )
    import_all_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    import_all_parser.add_argument("json_path", type=Path, help="Path to a paper.v1 JSON file produced by an agent.")
    import_all_parser.set_defaults(handler=handle_import_all)

    import_graph_parser = import_subparsers.add_parser("graph", help="Import a graph snapshot JSON file.")
    import_graph_parser.add_argument("json_path", type=Path, help="Path to a graph snapshot JSON file.")
    import_graph_parser.set_defaults(handler=handle_import_graph)

    import_workspace_parser = import_subparsers.add_parser(
        "workspace", help="Import a full workspace archive (.tar.gz) into the current data directory."
    )
    import_workspace_parser.add_argument(
        "archive_path", type=Path, help="Path to a workspace archive produced by `rks export workspace`."
    )
    import_workspace_parser.set_defaults(handler=handle_import_workspace)

    export_parser = subparsers.add_parser("export", help="Export graph data.")
    export_subparsers = export_parser.add_subparsers(dest="export_command", required=True)

    export_graph_parser = export_subparsers.add_parser("graph", help="Export a graph snapshot JSON file.")
    export_graph_parser.add_argument("json_path", type=Path, help="Destination path for the graph snapshot.")
    export_graph_parser.set_defaults(handler=handle_export_graph)

    export_workspace_parser = export_subparsers.add_parser(
        "workspace", help="Export a portable workspace archive (.tar.gz) with all data and files."
    )
    export_workspace_parser.add_argument(
        "archive_path", type=Path, help="Destination path for the workspace archive (e.g. my_workspace.tar.gz)."
    )
    export_workspace_parser.set_defaults(handler=handle_export_workspace)

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

    tasks_wait_parser = tasks_subparsers.add_parser(
        "wait",
        help="Block until a task reaches a terminal state (completed or failed).",
    )
    tasks_wait_parser.add_argument("task_id", help="Task ID, for example t_000001.")
    tasks_wait_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Maximum seconds to wait before giving up (default: 300).",
    )
    tasks_wait_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Poll interval in seconds (default: 2).",
    )
    tasks_wait_parser.set_defaults(handler=handle_tasks_wait)

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
    try:
        return int(args.handler(args))
    except ConfigError as exc:
        print(json.dumps({"error": "config_error", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": "internal_error", "type": type(exc).__name__, "message": str(exc)}, indent=2), file=sys.stderr)
        return 1


def handle_init(args: argparse.Namespace) -> int:
    data_dir = args.path.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    global_cfg = load_global_config()
    global_cfg["data_dir"] = str(data_dir)
    cfg_path = write_global_config(global_cfg)
    # Initialize the database
    from rks.storage import connect_db, initialize_db
    from rks.storage.db import apply_migrations
    db_path = data_dir / "rks.sqlite3"
    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        apply_migrations(conn)
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "data_dir": str(data_dir),
                "global_config": str(cfg_path),
                "db_path": str(db_path),
            },
            indent=2,
        )
    )
    return 0


def handle_init_db(args: argparse.Namespace) -> int:
    del args
    with _open_repository() as repo:
        print(json.dumps({"status": "ok", "db_initialized": True}, indent=2))
    return 0


def handle_clear(args: argparse.Namespace) -> int:
    import shutil
    paths = load_paths()
    if not args.yes:
        print(
            json.dumps(
                {
                    "status": "aborted",
                    "reason": "Pass --yes to confirm. This will permanently delete all papers, artifacts, and the database.",
                    "data_dir": str(paths.data_dir),
                },
                indent=2,
            )
        )
        return 1
    removed = []
    for target in (paths.db_path, paths.papers_dir, paths.artifacts_dir):
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(str(target))
    # Re-initialize an empty database so the workspace is immediately usable
    from rks.storage import connect_db, initialize_db
    from rks.storage.db import apply_migrations
    conn = connect_db(paths.db_path)
    try:
        initialize_db(conn)
        apply_migrations(conn)
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "data_dir": str(paths.data_dir),
                "removed": removed,
                "db_reinitialized": True,
            },
            indent=2,
        )
    )
    return 0


def handle_config_show(args: argparse.Namespace) -> int:
    del args
    gcfg_path = global_config_path()
    global_cfg = load_global_config()
    try:
        app_config = load_app_config()
        effective: dict = {
            "data_dir": str(app_config.data_dir),
            "reference_pdf_acquisition": app_config.reference_pdf_acquisition,
            "llm": {
                "base_url": app_config.llm_base_url,
                "model": app_config.llm_model,
                "api_key_env": app_config.llm_api_key_env,
            },
        }
    except ConfigError:
        effective = None
    print(
        json.dumps(
            {
                "global_config_path": str(gcfg_path),
                "global_config_exists": gcfg_path.exists(),
                "effective": effective,
                "raw_global_config": global_cfg,
            },
            indent=2,
        )
    )
    return 0


def handle_config_set_data_dir(args: argparse.Namespace) -> int:
    data_dir = args.path.expanduser().resolve()
    global_cfg = load_global_config()
    old_value = global_cfg.get("data_dir")
    global_cfg["data_dir"] = str(data_dir)
    cfg_path = write_global_config(global_cfg)
    print(
        json.dumps(
            {
                "status": "ok",
                "global_config": str(cfg_path),
                "data_dir": str(data_dir),
                "previous_data_dir": old_value,
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
    gcfg_path = global_config_path()
    global_cfg_exists = gcfg_path.exists()
    global_cfg_has_data_dir = "data_dir" in load_global_config()

    try:
        app_config = load_app_config()
        paths = load_paths()
        data_dir_exists = paths.data_dir.exists()
        db_exists = paths.db_path.exists()
        data_dir_str = str(paths.data_dir)
        db_path_str = str(paths.db_path)
    except ConfigError:
        data_dir_exists = False
        db_exists = False
        data_dir_str = None
        db_path_str = None

    checks = {
        "global_config": {
            "ok": global_cfg_has_data_dir,
            "path": str(gcfg_path),
        },
        "data_dir": {
            "ok": data_dir_exists,
            "path": data_dir_str,
        },
        "database": {
            "ok": db_exists,
            "path": db_path_str,
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
            "global_config": str(gcfg_path),
            "data_dir": data_dir_str,
            "db_path": db_path_str,
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
    if not checks["global_config"]["ok"]:
        actions.append("rks init <path>  # set your data directory")
    elif not checks["data_dir"]["ok"] or not checks["database"]["ok"]:
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


def handle_stats(args: argparse.Namespace) -> int:
    del args
    with _open_session() as session:
        payload = _operations(session).workspace_stats()
    print(json.dumps(payload, indent=2))
    return 0


def handle_evaluate_baseline(args: argparse.Namespace) -> int:
    spec = _load_json_object(args.spec_path, "baseline spec")
    checks = _normalize_baseline_checks(spec)
    with _open_session() as session:
        metrics = _operations(session).extraction_quality_report()
    evaluation = _evaluate_baseline_metrics(metrics, checks)
    payload = {
        "baseline_name": spec.get("name"),
        "spec_path": str(args.spec_path.resolve()),
        "passed": evaluation["passed"],
        "check_count": len(evaluation["checks"]),
        "failed_check_count": len(evaluation["failed_checks"]),
        "failed_checks": evaluation["failed_checks"],
        "checks": evaluation["checks"],
        "metrics": metrics,
    }
    print(json.dumps(payload, indent=2))
    return 0 if evaluation["passed"] else 1


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


def handle_papers_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        papers = session.papers.list_recent_papers(
            limit=args.limit,
            offset=args.offset,
            sort_by=args.sort,
            order=args.order,
            tag=args.tag,
        )
        total = session.papers.count_papers(tag=args.tag)
        payload_papers = [_paper_with_tags_payload(session.papers, paper) for paper in papers]
    payload = {
        "count": len(papers),
        "total_count": total,
        "limit": args.limit,
        "offset": args.offset,
        "sort": args.sort,
        "order": args.order,
        "tag": args.tag,
        "papers": payload_papers,
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_mark(args: argparse.Namespace) -> int:
    with _open_session() as session:
        added = session.papers.add_tag(args.paper_id, args.tag)
        paper = session.papers.get_paper(args.paper_id)
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = {
        "paper_id": paper.id,
        "tag": args.tag.strip().lower(),
        "added": added,
        "tags": tags,
        "paper": _paper_to_payload(paper),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_unmark(args: argparse.Namespace) -> int:
    with _open_session() as session:
        deleted = session.papers.remove_tag(args.paper_id, args.tag)
        paper = session.papers.get_paper(args.paper_id)
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = {
        "paper_id": paper.id,
        "tag": args.tag.strip().lower(),
        "deleted": deleted,
        "tags": tags,
        "paper": _paper_to_payload(paper),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_tags(args: argparse.Namespace) -> int:
    with _open_session() as session:
        paper = session.papers.get_paper(args.paper_id)
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = {
        "paper_id": paper.id,
        "tags": tags,
        "paper": _paper_to_payload(paper),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_read_later(args: argparse.Namespace) -> int:
    with _open_session() as session:
        papers = session.papers.list_recent_papers(
            limit=args.limit,
            offset=args.offset,
            sort_by=args.sort,
            order=args.order,
            tag="read_later",
        )
        total = session.papers.count_papers(tag="read_later")
        payload_papers = [_paper_with_tags_payload(session.papers, paper) for paper in papers]
    payload = {
        "count": len(papers),
        "total_count": total,
        "limit": args.limit,
        "offset": args.offset,
        "sort": args.sort,
        "order": args.order,
        "tag": "read_later",
        "papers": payload_papers,
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_find_duplicates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).find_duplicate_papers(mode=args.mode)
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_merge(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).merge_papers(
            args.target_paper_id,
            args.source_paper_id,
            prefer=args.prefer,
        )
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


def handle_import_all(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        counts = import_extract_all_result(
            paths=paths,
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            method_repo=session.methods,
            dataset_repo=session.datasets,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_all", None)
        if task is not None:
            record_task_report(session.papers, paths, task, note="Imported agent combined result.")
    print(json.dumps({"paper_id": args.paper_id, "mode": "agent", **counts}, indent=2))
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


def handle_import_methods(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        methods = import_methods_result(
            paths=paths,
            paper_repo=session.papers,
            claim_repo=session.claims,
            concept_repo=session.concepts,
            edge_repo=session.edges,
            method_repo=session.methods,
            dataset_repo=session.datasets,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_methods", None)
        if task is not None:
            record_task_report(session.papers, paths, task, note="Imported agent methods result.")
    print(json.dumps(_methods_payload(args.paper_id, "agent", methods), indent=2))
    return 0


def handle_import_datasets(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        datasets = import_datasets_result(
            paths=paths,
            paper_repo=session.papers,
            claim_repo=session.claims,
            edge_repo=session.edges,
            dataset_repo=session.datasets,
            method_repo=session.methods,
            paper_id=args.paper_id,
            json_path=args.json_path,
        )
        task = session.tasks.complete_latest_task(args.paper_id, "extract_datasets", None)
        if task is not None:
            record_task_report(session.papers, paths, task, note="Imported agent datasets result.")
    print(json.dumps(_datasets_payload(args.paper_id, "agent", datasets), indent=2))
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


def handle_export_workspace(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        payload = export_workspace(session.papers.conn, paths.data_dir, args.archive_path)
    print(json.dumps(payload, indent=2))
    return 0


def handle_import_workspace(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        payload = import_workspace(session.papers.conn, paths.data_dir, args.archive_path)
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


def handle_tasks_wait(args: argparse.Namespace) -> int:
    import time

    terminal = {"completed", "failed"}
    deadline = time.monotonic() + args.timeout
    while True:
        with _open_session() as session:
            task = session.tasks.get_task(args.task_id)
        if task.status in terminal:
            print(json.dumps(_task_payload(task), indent=2))
            return 0 if task.status == "completed" else 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                json.dumps(
                    {
                        "error": "timeout",
                        "message": f"Task {args.task_id} did not reach a terminal state within {args.timeout}s.",
                        "task": _task_payload(task),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        time.sleep(min(args.interval, remaining))


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


def _paper_with_tags_payload(paper_repo: PaperRepository, paper) -> dict:
    payload = _paper_to_payload(paper)
    payload["tags"] = paper_repo.list_tags_for_paper(paper.id)
    return payload


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


def _run_pipeline_if_configured(session, paths, paper_id: str) -> dict | None:
    """Run post-ingest pipeline when auto_extract_mode != 'none'."""
    app_config = load_app_config()
    mode = app_config.auto_extract_mode
    if mode == "none":
        return None
    provider = OpenAICompatibleLlmProvider(load_llm_config()) if mode == "llm-api" else None
    return run_post_ingest_pipeline(
        paths=paths,
        paper_repo=session.papers,
        claim_repo=session.claims,
        concept_repo=session.concepts,
        edge_repo=session.edges,
        method_repo=session.methods,
        dataset_repo=session.datasets,
        task_repo=session.tasks,
        paper_id=paper_id,
        mode=mode,
        provider=provider,
    )


def _claims_payload(paper_id: str, mode: str, claims: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "claim_count": len(claims),
        "claim_ids": [claim.id for claim in claims],
    }


def _methods_payload(paper_id: str, mode: str, methods: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "method_count": len(methods),
        "method_ids": [method.id for method in methods],
    }


def _datasets_payload(paper_id: str, mode: str, datasets: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "dataset_count": len(datasets),
        "dataset_ids": [dataset.id for dataset in datasets],
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


def _load_json_object(path: Path, label: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return payload


def _normalize_baseline_checks(spec: dict) -> dict:
    checks = spec.get("checks")
    if checks is None:
        checks = {
            key: value
            for key, value in spec.items()
            if key not in {"name", "description", "version"}
        }
    if not isinstance(checks, dict) or not checks:
        raise ValueError("Baseline spec must define at least one check under `checks`.")
    allowed = {
        "min_paper_count",
        "min_total_claims",
        "min_mean_claims_per_paper",
        "max_zero_claim_rate",
        "required_predicates",
        "required_extraction_modes",
        "min_predicate_counts",
        "min_extraction_mode_counts",
        "per_paper_min_claims",
    }
    unknown = sorted(set(checks) - allowed)
    if unknown:
        raise ValueError(f"Unsupported baseline check keys: {', '.join(unknown)}")
    return checks


def _evaluate_baseline_metrics(metrics: dict, checks: dict) -> dict:
    paper_count = int(metrics.get("paper_count", 0))
    total_claims = int(metrics.get("total_claims", 0))
    mean_claims = float((metrics.get("claims_per_paper") or {}).get("mean", 0.0))
    zero_claim_count = len(metrics.get("zero_claim_papers", []))
    zero_claim_rate = (zero_claim_count / paper_count) if paper_count else 0.0
    predicate_distribution = metrics.get("predicate_distribution") or {}
    mode_distribution = metrics.get("extraction_mode_distribution") or {}
    per_paper_claims = {
        item["paper_id"]: int(item.get("claim_count", 0))
        for item in metrics.get("per_paper", [])
        if isinstance(item, dict) and "paper_id" in item
    }
    # Fallback when per-paper details are not returned by metrics payload.
    if not per_paper_claims:
        per_paper_claims = {}

    results: list[dict] = []

    def record(check: str, expected, actual, passed: bool) -> None:
        results.append(
            {
                "check": check,
                "expected": expected,
                "actual": actual,
                "passed": bool(passed),
            }
        )

    if "min_paper_count" in checks:
        threshold = int(checks["min_paper_count"])
        record("min_paper_count", {">=": threshold}, paper_count, paper_count >= threshold)
    if "min_total_claims" in checks:
        threshold = int(checks["min_total_claims"])
        record("min_total_claims", {">=": threshold}, total_claims, total_claims >= threshold)
    if "min_mean_claims_per_paper" in checks:
        threshold = float(checks["min_mean_claims_per_paper"])
        record("min_mean_claims_per_paper", {">=": threshold}, mean_claims, mean_claims >= threshold)
    if "max_zero_claim_rate" in checks:
        threshold = float(checks["max_zero_claim_rate"])
        record("max_zero_claim_rate", {"<=": threshold}, round(zero_claim_rate, 4), zero_claim_rate <= threshold)
    if "required_predicates" in checks:
        required = list(checks["required_predicates"])
        missing = [name for name in required if predicate_distribution.get(name, 0) <= 0]
        record("required_predicates", {"present": required}, {"missing": missing}, len(missing) == 0)
    if "required_extraction_modes" in checks:
        required = list(checks["required_extraction_modes"])
        missing = [name for name in required if mode_distribution.get(name, 0) <= 0]
        record("required_extraction_modes", {"present": required}, {"missing": missing}, len(missing) == 0)
    if "min_predicate_counts" in checks:
        expected = dict(checks["min_predicate_counts"])
        for predicate, threshold in expected.items():
            actual = int(predicate_distribution.get(predicate, 0))
            record(
                f"min_predicate_counts.{predicate}",
                {">=": int(threshold)},
                actual,
                actual >= int(threshold),
            )
    if "min_extraction_mode_counts" in checks:
        expected = dict(checks["min_extraction_mode_counts"])
        for mode, threshold in expected.items():
            actual = int(mode_distribution.get(mode, 0))
            record(
                f"min_extraction_mode_counts.{mode}",
                {">=": int(threshold)},
                actual,
                actual >= int(threshold),
            )
    if "per_paper_min_claims" in checks:
        expected = dict(checks["per_paper_min_claims"])
        for paper_id, threshold in expected.items():
            actual = int(per_paper_claims.get(paper_id, 0))
            record(
                f"per_paper_min_claims.{paper_id}",
                {">=": int(threshold)},
                actual,
                actual >= int(threshold),
            )

    failed = [item for item in results if not item["passed"]]
    return {
        "passed": len(failed) == 0,
        "checks": results,
        "failed_checks": failed,
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
        paths = load_paths()
        if stage == "text":
            paper = session.papers.get_paper(paper_id)
            if mode == "llm-api":
                artifact = extract_text_with_llm(
                    repo=session.papers,
                    paths=paths,
                    paper=paper,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _artifact_payload(paper_id, mode, artifact)
            request = create_text_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_text", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract text --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "claims":
            if mode == "llm-api":
                claims = extract_claims_with_llm(
                    paths, session.papers, session.claims, session.concepts, session.edges, paper_id,
                    OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _claims_payload(paper_id, mode, claims)
            request = create_claims_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_claims", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract claims --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "methods":
            if mode == "llm-api":
                methods = extract_methods_with_llm(
                    paths=paths, paper_repo=session.papers, claim_repo=session.claims,
                    concept_repo=session.concepts, edge_repo=session.edges,
                    method_repo=session.methods, dataset_repo=session.datasets,
                    paper_id=paper_id, provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _methods_payload(paper_id, mode, methods)
            request = create_methods_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_methods", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract methods --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "datasets":
            if mode == "llm-api":
                datasets = extract_datasets_with_llm(
                    paths=paths, paper_repo=session.papers, claim_repo=session.claims,
                    edge_repo=session.edges, dataset_repo=session.datasets,
                    method_repo=session.methods, paper_id=paper_id,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _datasets_payload(paper_id, mode, datasets)
            request = create_datasets_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_datasets", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract datasets --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "summary":
            if mode == "llm-api":
                return persist_summary_artifact(
                    session.papers,
                    paths,
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
                session.papers, session.claims, session.concepts, paths, paper_id
            )
            task = session.tasks.create_task(
                "summarize_paper", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract summary --mode agent.")
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
