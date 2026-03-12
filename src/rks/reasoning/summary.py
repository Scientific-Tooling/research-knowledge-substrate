from __future__ import annotations

import json
from pathlib import Path

from rks.config import AppPaths
from rks.storage import ClaimRepository, ConceptRepository, PaperRepository


def summarize_paper_heuristic(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    paper_id: str,
) -> dict:
    paper = paper_repo.get_paper(paper_id)
    claims = claim_repo.list_claims_for_paper(paper_id)
    concepts = concept_repo.list_for_paper(paper_id)

    sentences = []
    if paper.abstract:
        sentences.append(f"Abstract: {paper.abstract}")
    if claims:
        claim_bits = []
        for claim in claims[:5]:
            subject = _subject_name(concept_repo, claim)
            obj = _object_name(concept_repo, claim)
            if subject and obj:
                claim_bits.append(f"{subject} {claim.predicate} {obj}")
            else:
                claim_bits.append(claim.text)
        sentences.append("Key claims: " + "; ".join(claim_bits) + ".")
    if concepts:
        sentences.append("Main concepts: " + ", ".join(concept.name for concept in concepts[:6]) + ".")

    payload = {
        "summary": " ".join(sentences).strip() or f"{paper.title} has no available summary yet.",
        "evidence_claim_ids": [claim.id for claim in claims[:5]],
        "open_questions": [] if claims else ["No extracted claims are available yet."],
        "mode": "heuristic",
    }
    return persist_summary_artifact(
        paper_repo=paper_repo,
        paths=paths,
        paper_id=paper_id,
        payload=payload,
        artifact_type="paper_summary",
        filename="paper_summary.json",
    )


def build_summary_input(
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    paper_id: str,
) -> dict:
    paper = paper_repo.get_paper(paper_id)
    claims = claim_repo.list_claims_for_paper(paper_id)
    concepts = concept_repo.list_for_paper(paper_id)
    return {
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "source_type": paper.source_type,
            "source_ref": paper.source_ref,
        },
        "claims": [
            {
                "id": claim.id,
                "text": claim.text,
                "subject": _subject_name(concept_repo, claim),
                "predicate": claim.predicate,
                "object": _object_name(concept_repo, claim),
                "confidence": claim.confidence,
            }
            for claim in claims
        ],
        "concepts": [concept.name for concept in concepts],
    }


def persist_summary_artifact(
    paper_repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    payload: dict,
    artifact_type: str,
    filename: str,
) -> dict:
    paper_dir = Path(paths.papers_dir / paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    summary_path = paper_dir / filename
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifact = paper_repo.create_artifact(
        paper_id=paper_id,
        artifact_type=artifact_type,
        path=summary_path,
        format_name="json",
        metadata={"mode": payload.get("mode"), "evidence_claim_count": len(payload.get("evidence_claim_ids", []))},
    )
    return {
        "paper_id": paper_id,
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
        "summary": payload["summary"],
        "evidence_claim_ids": payload.get("evidence_claim_ids", []),
        "open_questions": payload.get("open_questions", []),
    }


def _subject_name(concept_repo: ConceptRepository, claim) -> str | None:
    context = json.loads(claim.context_json or "{}")
    if claim.subject_concept_id:
        return concept_repo.get_concept(claim.subject_concept_id).name
    return context.get("subject_text")


def _object_name(concept_repo: ConceptRepository, claim) -> str | None:
    if claim.object_concept_id:
        return concept_repo.get_concept(claim.object_concept_id).name
    return claim.object_text
