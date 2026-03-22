from __future__ import annotations

import json
from pathlib import Path

from rks.config import AppPaths
from rks.extraction.claims import persist_claims_for_paper
from rks.extraction.entities import extract_all_with_llm, extract_datasets_with_llm, extract_methods_with_llm
from rks.extraction.text import build_text_source_input, write_text_artifact
from rks.llm import (
    CLAIMS_SCHEMA_VERSION,
    DATASETS_SCHEMA_VERSION,
    METHODS_SCHEMA_VERSION,
    PAPER_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    TEXT_SCHEMA_VERSION,
    build_dual_track_request,
    validate_claims_result_payload,
    validate_datasets_result_payload,
    validate_methods_result_payload,
    validate_paper_result_payload,
    validate_summary_result_payload,
    validate_text_result_payload,
)
from rks.reasoning.summary import build_summary_input, persist_summary_artifact
from rks.storage import ClaimRepository, ConceptRepository, DatasetRepository, EdgeRepository, MethodRepository, PaperRepository
from rks.utils import ensure_dir, utc_now


def create_text_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    input_payload = build_text_source_input(paper)
    request = build_dual_track_request(
        task="extract_text",
        paper_id=paper_id,
        instruction=(
            "Extract readable research text from the PDF document. "
            "The source PDF path is provided in `source_pdf` — read it directly "
            "for best results. The `rough_text` field contains a PDF-extracted "
            "pre-extraction that may be incomplete. Return JSON with keys: "
            "`text`, `paragraphs`, `warnings`."
        ),
        input_payload=input_payload,
        expected_output_schema={
            "text": "string",
            "paragraphs": ["string"],
            "warnings": ["string"],
        },
        schema_version=TEXT_SCHEMA_VERSION,
    )
    # Surface the PDF path at the top level so agents can read it directly
    # without parsing the nested input payload.
    if input_payload.get("source_pdf"):
        request["source_pdf"] = input_payload["source_pdf"]
    return _write_request_artifact(repo, paths, paper_id, "agent_text_request", "agent_text_request.json", request)


def create_claims_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        raise ValueError(f"Paper {paper_id} does not have an extracted text artifact.")
    artifact = repo.get_artifact(paper.text_artifact_id)
    text_payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    request = build_dual_track_request(
        task="extract_claims",
        paper_id=paper_id,
        instruction=(
            "Extract structured research claims. Return JSON with top-level key `claims`. "
            "Each claim must contain `text`, `predicate`, `object_text`, `context`, "
            "`evidence`, and `confidence`. "
            "Put the claim subject in `context.subject_text`. "
            "Put the paper section in `context.section` (abstract, introduction, method, "
            "experiments, results, conclusion, or discussion). "
            "Put the dataset name (if any) in `context.dataset`. "
            "Put a short verbatim supporting quote in `evidence.quote`. "
            "Also include an optional top-level `concept_aliases` list. "
            "Each entry must have `canonical` (the preferred concept name) and `aliases` "
            "(a list of synonymous terms found in this paper, e.g. abbreviations, full names, "
            "or alternate spellings). This reduces concept fragmentation across papers."
        ),
        input_payload=text_payload,
        expected_output_schema={
            "claims": [
                {
                    "text": "string",
                    "predicate": "string",
                    "object_text": "string|null",
                    "context": {
                        "subject_text": "string",
                        "section": "abstract|introduction|method|experiments|results|conclusion|discussion",
                        "dataset": "string|null",
                    },
                    "evidence": {
                        "paper_id": paper_id,
                        "quote": "string|null",
                    },
                    "confidence": "float",
                }
            ],
            "concept_aliases": [
                {
                    "canonical": "string",
                    "aliases": ["string"],
                }
            ],
        },
        schema_version=CLAIMS_SCHEMA_VERSION,
    )
    return _write_request_artifact(
        repo,
        paths,
        paper_id,
        "agent_claims_request",
        "agent_claims_request.json",
        request,
    )


def create_methods_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        raise ValueError(f"Paper {paper_id} does not have an extracted text artifact.")
    artifact = repo.get_artifact(paper.text_artifact_id)
    text_payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    request = build_dual_track_request(
        task="extract_methods",
        paper_id=paper_id,
        instruction=(
            "Extract methods, models, algorithms, architectures, and frameworks from this paper. "
            "Return JSON with top-level key `methods`. "
            "Each method must contain `name` and `description`. "
            "Set `proposed_by_this_paper` to true only if this paper introduces the method. "
            "List known alternate names in `aliases`."
        ),
        input_payload=text_payload,
        expected_output_schema={
            "methods": [
                {
                    "name": "string",
                    "description": "string",
                    "proposed_by_this_paper": "bool",
                    "aliases": ["string"],
                }
            ]
        },
        schema_version=METHODS_SCHEMA_VERSION,
    )
    return _write_request_artifact(
        repo,
        paths,
        paper_id,
        "agent_methods_request",
        "agent_methods_request.json",
        request,
    )


def import_methods_result(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    method_repo: MethodRepository,
    dataset_repo: DatasetRepository,
    paper_id: str,
    json_path: Path,
):
    raw = validate_methods_result_payload(json.loads(json_path.read_text(encoding="utf-8")))
    return extract_methods_with_llm(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        concept_repo=concept_repo,
        edge_repo=edge_repo,
        method_repo=method_repo,
        dataset_repo=dataset_repo,
        paper_id=paper_id,
        provider=_StaticMethodsProvider(raw),
    )


class _StaticMethodsProvider:
    """Wraps a pre-validated list so it can be passed where a live provider is expected."""

    def __init__(self, methods: list[dict]):
        self._methods = methods

    def parse_methods(self, _text_payload: dict) -> list[dict]:
        return self._methods


def create_datasets_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        raise ValueError(f"Paper {paper_id} does not have an extracted text artifact.")
    artifact = repo.get_artifact(paper.text_artifact_id)
    text_payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    request = build_dual_track_request(
        task="extract_datasets",
        paper_id=paper_id,
        instruction=(
            "Extract named datasets used or referenced in this paper. "
            "Return JSON with top-level key `datasets`. "
            "Each dataset must contain `name` and `description`. "
            "Set `used_for` to train, eval, or both. "
            "Set `source` to a URL or citation if mentioned."
        ),
        input_payload=text_payload,
        expected_output_schema={
            "datasets": [
                {
                    "name": "string",
                    "description": "string",
                    "used_for": "train|eval|both|null",
                    "source": "string|null",
                }
            ]
        },
        schema_version=DATASETS_SCHEMA_VERSION,
    )
    return _write_request_artifact(
        repo,
        paths,
        paper_id,
        "agent_datasets_request",
        "agent_datasets_request.json",
        request,
    )


def create_extract_all_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    input_payload = build_text_source_input(paper)
    request = build_dual_track_request(
        task="extract_all",
        paper_id=paper_id,
        instruction=(
            "Perform a full single-pass extraction of the paper. "
            "Return a JSON object with all of the following top-level keys: "
            "`text` (string), `paragraphs` (list), `warnings` (list), "
            "`claims` (list), `methods` (list), `datasets` (list), "
            "`summary` (string), `evidence_claim_ids` (list), `open_questions` (list). "
            "Each claim must include text, predicate, object_text, context (subject_text, section, dataset), "
            "evidence (quote), and confidence. "
            "Each method must include name, description, proposed_by_this_paper, aliases. "
            "Each dataset must include name, description, used_for, source."
        ),
        input_payload=input_payload,
        expected_output_schema={
            "text": "string",
            "paragraphs": ["string"],
            "warnings": ["string"],
            "claims": [{"text": "string", "predicate": "string", "object_text": "string|null",
                        "context": {"subject_text": "string", "section": "string|null", "dataset": "string|null"},
                        "evidence": {"quote": "string|null"}, "confidence": "float"}],
            "methods": [{"name": "string", "description": "string",
                         "proposed_by_this_paper": "bool", "aliases": ["string"]}],
            "datasets": [{"name": "string", "description": "string",
                          "used_for": "train|eval|both|null", "source": "string|null"}],
            "summary": "string",
            "evidence_claim_ids": ["string"],
            "open_questions": ["string"],
        },
        schema_version=PAPER_SCHEMA_VERSION,
    )
    if input_payload.get("source_pdf"):
        request["source_pdf"] = input_payload["source_pdf"]
    return _write_request_artifact(
        repo, paths, paper_id, "agent_extract_all_request", "agent_extract_all_request.json", request
    )


def import_extract_all_result(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    method_repo: MethodRepository,
    dataset_repo: DatasetRepository,
    paper_id: str,
    json_path: Path,
) -> dict:
    raw = validate_paper_result_payload(json.loads(json_path.read_text(encoding="utf-8")))
    return extract_all_with_llm(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        concept_repo=concept_repo,
        edge_repo=edge_repo,
        method_repo=method_repo,
        dataset_repo=dataset_repo,
        paper_id=paper_id,
        provider=_StaticAllProvider(raw),
    )


class _StaticAllProvider:
    """Wraps a pre-validated combined payload so it can be passed to extract_all_with_llm."""

    def __init__(self, paper_result: dict):
        self._paper_result = paper_result

    def extract_all(self, _text_source: dict) -> dict:
        return self._paper_result


def import_datasets_result(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    edge_repo: EdgeRepository,
    dataset_repo: DatasetRepository,
    method_repo: MethodRepository,
    paper_id: str,
    json_path: Path,
):
    raw = validate_datasets_result_payload(json.loads(json_path.read_text(encoding="utf-8")))
    return extract_datasets_with_llm(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        edge_repo=edge_repo,
        dataset_repo=dataset_repo,
        method_repo=method_repo,
        paper_id=paper_id,
        provider=_StaticDatasetsProvider(raw),
    )


class _StaticDatasetsProvider:
    """Wraps a pre-validated list so it can be passed where a live provider is expected."""

    def __init__(self, datasets: list[dict]):
        self._datasets = datasets

    def parse_datasets(self, _text_payload: dict) -> list[dict]:
        return self._datasets


def create_summary_request(
    repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    paths: AppPaths,
    paper_id: str,
) -> dict:
    request = build_dual_track_request(
        task="summarize_paper",
        paper_id=paper_id,
        instruction=(
            "Write a concise research summary grounded in the input claims and concepts. "
            "Return JSON with keys `summary`, `evidence_claim_ids`, `evidence_paper_ids`, "
            "`citations`, and `open_questions`."
        ),
        input_payload=build_summary_input(repo, claim_repo, concept_repo, paper_id),
        expected_output_schema={
            "summary": "string",
            "evidence_claim_ids": ["string"],
            "evidence_paper_ids": ["string"],
            "citations": [{"claim_id": "string", "paper_id": "string"}],
            "open_questions": ["string"],
        },
        schema_version=SUMMARY_SCHEMA_VERSION,
    )
    return _write_request_artifact(
        repo,
        paths,
        paper_id,
        "agent_summary_request",
        "agent_summary_request.json",
        request,
    )


def import_text_result(repo: PaperRepository, paths: AppPaths, paper_id: str, json_path: Path):
    payload = validate_text_result_payload(json.loads(json_path.read_text(encoding="utf-8")))
    payload.setdefault("extractor", "agent")
    payload.setdefault("warnings", [])
    payload.setdefault("source_pdf", None)
    payload.setdefault("paragraphs", [payload.get("text", "")] if payload.get("text") else [])
    payload.setdefault("schema_version", TEXT_SCHEMA_VERSION)
    return write_text_artifact(repo=repo, paths=paths, paper_id=paper_id, payload=payload)


def import_claims_result(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
    json_path: Path,
):
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    claims = validate_claims_result_payload(raw)
    for claim in claims:
        evidence = dict(claim.get("evidence", {}))
        evidence.setdefault("schema_version", CLAIMS_SCHEMA_VERSION)
        claim["evidence"] = evidence

    # Apply concept aliases before claim persistence so concept resolution benefits immediately.
    concept_aliases = raw.get("concept_aliases", []) if isinstance(raw, dict) else []
    for entry in concept_aliases:
        canonical = entry.get("canonical", "").strip()
        aliases = [a for a in entry.get("aliases", []) if isinstance(a, str) and a.strip()]
        if not canonical:
            continue
        concept = concept_repo.get_or_create(canonical)
        if aliases:
            concept_repo.add_aliases(concept.id, aliases)

    return persist_claims_for_paper(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        concept_repo=concept_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        claims=claims,
        extractor="agent",
    )


def import_summary_result(repo: PaperRepository, paths: AppPaths, paper_id: str, json_path: Path):
    payload = validate_summary_result_payload(json.loads(json_path.read_text(encoding="utf-8")))
    payload.setdefault("mode", "agent")
    payload.setdefault("schema_version", SUMMARY_SCHEMA_VERSION)
    return persist_summary_artifact(
        paper_repo=repo,
        paths=paths,
        paper_id=paper_id,
        payload=payload,
        artifact_type="paper_summary",
        filename="paper_summary.json",
    )


def record_task_report(
    repo: PaperRepository,
    paths: AppPaths,
    task,
    *,
    note: str | None = None,
    error: dict | None = None,
) -> dict:
    report_path = ensure_dir(paths.papers_dir / task.paper_id) / "agent_execution_reports.json"
    payload = _load_task_report_payload(report_path)
    reports = {report["task_id"]: report for report in payload.get("reports", [])}
    report = reports.get(task.id)
    if report is None:
        report = {
            "task_id": task.id,
            "task_type": task.task_type,
            "paper_id": task.paper_id,
            "mode": task.mode,
            "spec_version": task.spec_version,
            "schema_version": task.schema_version,
            "events": [],
        }
        reports[task.id] = report

    event = {
        "status": task.status,
        "at": utc_now(),
        "request_artifact_id": task.request_artifact_id,
        "result_artifact_id": task.result_artifact_id,
        "note": note,
        "error": error,
        "recovery_commands": _task_recovery_commands(task.task_type, task.status, task.paper_id, task.id),
    }
    report.update(
        {
            "current_status": task.status,
            "request_artifact_id": task.request_artifact_id,
            "result_artifact_id": task.result_artifact_id,
            "last_error": error,
            "recovery_commands": event["recovery_commands"],
        }
    )
    report["events"].append(event)

    serialized = {
        "updated_at": utc_now(),
        "report_count": len(reports),
        "reports": sorted(reports.values(), key=lambda item: item["task_id"]),
    }
    report_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    repo.create_artifact(
        paper_id=task.paper_id,
        artifact_type="agent_execution_reports",
        path=report_path,
        format_name="json",
        metadata={
            "report_count": serialized["report_count"],
            "updated_at": serialized["updated_at"],
        },
    )
    return report


def load_task_reports(repo: PaperRepository, paper_id: str) -> list[dict]:
    for artifact in repo.get_artifacts_for_paper(paper_id):
        if artifact.artifact_type != "agent_execution_reports":
            continue
        path = Path(artifact.path)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("reports", [])
    return []


def _write_request_artifact(
    repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    artifact_type: str,
    filename: str,
    payload: dict,
) -> dict:
    paper_dir = ensure_dir(paths.papers_dir / paper_id)
    request_path = paper_dir / filename
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifact = repo.create_artifact(
        paper_id=paper_id,
        artifact_type=artifact_type,
        path=request_path,
        format_name="json",
        metadata={
            "task": payload["task"],
            "spec_version": payload["spec_version"],
            "schema_version": payload["schema_version"],
        },
    )
    return {
        "paper_id": paper_id,
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
        "task": payload["task"],
        "spec_version": payload["spec_version"],
        "schema_version": payload["schema_version"],
        "instruction": payload["instruction"],
    }


def _load_task_report_payload(path: Path) -> dict:
    if not path.exists():
        return {"reports": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _task_recovery_commands(task_type: str, status: str, paper_id: str, task_id: str) -> list[str]:
    commands = [f"rks tasks show {task_id}"]
    if status in {"queued", "running"}:
        commands.append(_task_import_command(task_type, paper_id))
        return [command for command in commands if command]
    if status == "failed":
        commands.append(_task_retry_command(task_type, paper_id))
        return [command for command in commands if command]
    return commands


def _task_import_command(task_type: str, paper_id: str) -> str | None:
    if task_type == "extract_text":
        return f"rks import text {paper_id} <agent-result.json>"
    if task_type == "extract_claims":
        return f"rks import claims {paper_id} <agent-result.json>"
    if task_type == "extract_methods":
        return f"rks import methods {paper_id} <agent-result.json>"
    if task_type == "extract_datasets":
        return f"rks import datasets {paper_id} <agent-result.json>"
    if task_type == "summarize_paper":
        return f"rks import summary {paper_id} <agent-result.json>"
    if task_type == "extract_all":
        return f"rks import all {paper_id} <agent-result.json>"
    return None


def _task_retry_command(task_type: str, paper_id: str) -> str | None:
    if task_type == "extract_text":
        return f"rks extract text {paper_id} --mode agent"
    if task_type == "extract_claims":
        return f"rks extract claims {paper_id} --mode agent"
    if task_type == "extract_methods":
        return f"rks extract methods {paper_id} --mode agent"
    if task_type == "extract_datasets":
        return f"rks extract datasets {paper_id} --mode agent"
    if task_type == "summarize_paper":
        return f"rks summarize paper {paper_id} --mode agent"
    if task_type == "extract_all":
        return f"rks extract all {paper_id} --mode agent"
    return None
