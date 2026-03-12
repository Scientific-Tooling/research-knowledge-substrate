from __future__ import annotations

import json
import re
from pathlib import Path

from rks.storage import ClaimRepository, PaperRepository


PREDICATE_KEYWORDS = {
    "outperforms": "outperforms",
    "improves": "improves",
    "reduces": "reduces",
    "increases": "increases",
    "enables": "enables",
    "requires": "requires",
    "supports": "supports",
    "replaces": "replaces",
}


def extract_claims_for_paper(
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    paper_id: str,
) -> list:
    paper = paper_repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        return []

    artifact = paper_repo.get_artifact(paper.text_artifact_id)
    payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    text = payload.get("text", "")
    claims = _extract_claim_dicts(text=text, paper_id=paper_id)
    return claim_repo.replace_claims_for_paper(paper_id, claims)


def _extract_claim_dicts(text: str, paper_id: str) -> list[dict]:
    normalized_text = " ".join(text.split())
    if not normalized_text:
        return []

    raw_sentences = re.split(r"(?<=[.!?])\s+", normalized_text)
    claims: list[dict] = []

    for sentence in raw_sentences:
        candidate = sentence.strip()
        if len(candidate) < 30:
            continue

        lowered = candidate.lower()
        predicate = _detect_predicate(lowered)
        if predicate is None:
            continue

        claims.append(
            {
                "text": candidate,
                "predicate": predicate,
                "object_text": None,
                "context": {"paper_id": paper_id},
                "evidence": {"paper_id": paper_id, "extraction": "heuristic"},
                "confidence": 0.35,
            }
        )

    return claims


def _detect_predicate(sentence: str) -> str | None:
    for keyword, predicate in PREDICATE_KEYWORDS.items():
        if keyword in sentence:
            return predicate
    if "show" in sentence or "demonstrate" in sentence:
        return "supports"
    return None
