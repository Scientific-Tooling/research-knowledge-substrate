from __future__ import annotations

import json
from pathlib import Path

from rks.config import AppPaths
from rks.extraction.claims import persist_claims_for_paper
from rks.extraction.text import build_text_source_input, write_text_artifact
from rks.llm import (
    build_dual_track_request,
    validate_claims_result_payload,
    validate_summary_result_payload,
    validate_text_result_payload,
)
from rks.reasoning.summary import build_summary_input, persist_summary_artifact
from rks.storage import ClaimRepository, ConceptRepository, EdgeRepository, PaperRepository
from rks.utils import ensure_dir, utc_now

TEXT_SCHEMA_VERSION = "text.v1"
CLAIMS_SCHEMA_VERSION = "claims.v1"
SUMMARY_SCHEMA_VERSION = "summary.v1"


def create_text_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    request = build_dual_track_request(
        task="extract_text",
        paper_id=paper_id,
        instruction=(
            "Extract readable research text from the input. Return JSON with keys: "
            "`text`, `paragraphs`, `warnings`."
        ),
        input_payload=build_text_source_input(paper),
        expected_output_schema={
            "text": "string",
            "paragraphs": ["string"],
            "warnings": ["string"],
        },
        schema_version=TEXT_SCHEMA_VERSION,
    )
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
            "`evidence`, and `confidence`. Put the claim subject in `context.subject_text`."
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
                    },
                    "evidence": {
                        "paper_id": paper_id,
                    },
                    "confidence": "float",
                }
            ]
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
    claims = validate_claims_result_payload(json.loads(json_path.read_text(encoding="utf-8")))
    for claim in claims:
        evidence = dict(claim.get("evidence", {}))
        evidence.setdefault("schema_version", CLAIMS_SCHEMA_VERSION)
        claim["evidence"] = evidence
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
    if task_type == "summarize_paper":
        return f"rks import summary {paper_id} <agent-result.json>"
    return None


def _task_retry_command(task_type: str, paper_id: str) -> str | None:
    if task_type == "extract_text":
        return f"rks extract text {paper_id} --mode agent"
    if task_type == "extract_claims":
        return f"rks extract claims {paper_id} --mode agent"
    if task_type == "summarize_paper":
        return f"rks summarize paper {paper_id} --mode agent"
    return None
