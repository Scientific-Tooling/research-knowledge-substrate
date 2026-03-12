from __future__ import annotations

import json
from pathlib import Path

from rks.config import AppPaths
from rks.extraction.claims import persist_claims_for_paper
from rks.extraction.text import build_text_source_input, write_text_artifact
from rks.storage import ClaimRepository, ConceptRepository, EdgeRepository, PaperRepository
from rks.utils import ensure_dir


def create_text_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    request = {
        "task": "extract_text",
        "paper_id": paper_id,
        "instruction": (
            "Extract readable research text from the input. Return JSON with keys: "
            "`text`, `paragraphs`, `warnings`."
        ),
        "input": build_text_source_input(paper),
        "expected_output_schema": {
            "text": "string",
            "paragraphs": ["string"],
            "warnings": ["string"],
        },
    }
    return _write_request_artifact(repo, paths, paper_id, "agent_text_request", "agent_text_request.json", request)


def create_claims_request(repo: PaperRepository, paths: AppPaths, paper_id: str) -> dict:
    paper = repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        raise ValueError(f"Paper {paper_id} does not have an extracted text artifact.")
    artifact = repo.get_artifact(paper.text_artifact_id)
    text_payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    request = {
        "task": "extract_claims",
        "paper_id": paper_id,
        "instruction": (
            "Extract structured research claims. Return JSON with top-level key `claims`. "
            "Each claim must contain `text`, `predicate`, `object_text`, `context`, "
            "`evidence`, and `confidence`. Put the claim subject in `context.subject_text`."
        ),
        "input": text_payload,
        "expected_output_schema": {
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
    }
    return _write_request_artifact(
        repo,
        paths,
        paper_id,
        "agent_claims_request",
        "agent_claims_request.json",
        request,
    )


def import_text_result(repo: PaperRepository, paths: AppPaths, paper_id: str, json_path: Path):
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload.setdefault("extractor", "agent")
    payload.setdefault("warnings", [])
    payload.setdefault("source_pdf", None)
    payload.setdefault("paragraphs", [payload.get("text", "")] if payload.get("text") else [])
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
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    claims = payload["claims"] if isinstance(payload, dict) and "claims" in payload else payload
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
        metadata={"task": payload["task"]},
    )
    return {
        "paper_id": paper_id,
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
        "instruction": payload["instruction"],
    }
