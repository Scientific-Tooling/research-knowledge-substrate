from __future__ import annotations

import json
import re
from pathlib import Path

from rks.config import AppPaths
from rks.concepts import link_claims_for_paper
from rks.storage import ClaimRepository, ConceptRepository, EdgeRepository, PaperRepository


PREDICATE_PATTERNS = [
    ("outperform", "outperforms"),
    ("outperforms", "outperforms"),
    ("improve", "improves"),
    ("improves", "improves"),
    ("reduce", "reduces"),
    ("reduces", "reduces"),
    ("increase", "increases"),
    ("increases", "increases"),
    ("enable", "enables"),
    ("enables", "enables"),
    ("require", "requires"),
    ("requires", "requires"),
    ("support", "supports"),
    ("supports", "supports"),
    ("replace", "replaces"),
    ("replaces", "replaces"),
]


def extract_claims_for_paper(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
) -> list:
    paper = paper_repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        return []

    artifact = paper_repo.get_artifact(paper.text_artifact_id)
    payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    text = payload.get("text", "")
    claim_candidates = _extract_candidate_sentences(text=text)
    normalized_claims = [_normalize_sentence(candidate) for candidate in claim_candidates]
    claims = _extract_claim_dicts(text=text, paper_id=paper_id)
    _write_claim_stage_artifact(paper_repo, artifact.path, paper_id, "claim_candidates", claim_candidates)
    _write_claim_stage_artifact(paper_repo, artifact.path, paper_id, "normalized_claims", normalized_claims)
    return persist_claims_for_paper(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        concept_repo=concept_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        claims=claims,
        extractor="heuristic",
    )


def extract_claims_with_llm(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
    provider,
) -> list:
    paper = paper_repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        return []
    artifact = paper_repo.get_artifact(paper.text_artifact_id)
    text_payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    claims = provider.parse_claims(text_payload)
    return persist_claims_for_paper(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        concept_repo=concept_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        claims=claims,
        extractor="llm_api",
    )


def persist_claims_for_paper(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
    claims: list[dict],
    extractor: str,
) -> list:
    paper = paper_repo.get_paper(paper_id)
    paper_dir = Path(paths.papers_dir / paper.id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    structured_claims_path = paper_dir / "structured_claims.json"
    structured_claims_path.write_text(json.dumps(claims, indent=2), encoding="utf-8")
    paper_repo.create_artifact(
        paper_id=paper_id,
        artifact_type="structured_claims",
        path=structured_claims_path,
        format_name="json",
        metadata={"count": len(claims), "extractor": extractor},
    )

    stored_claims = claim_repo.replace_claims_for_paper(paper_id, claims)
    if stored_claims:
        link_claims_for_paper(
            paper_repo=paper_repo,
            claim_repo=claim_repo,
            concept_repo=concept_repo,
            edge_repo=edge_repo,
            paper_id=paper_id,
        )
    return claim_repo.list_claims_for_paper(paper_id)


def _write_claim_stage_artifact(paper_repo: PaperRepository, text_artifact_path: str, paper_id: str, artifact_type: str, payload) -> None:
    path = Path(text_artifact_path).parent / f"{artifact_type}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paper_repo.create_artifact(
        paper_id=paper_id,
        artifact_type=artifact_type,
        path=path,
        format_name="json",
        metadata={"count": len(payload) if hasattr(payload, "__len__") else None},
    )


def _extract_claim_dicts(text: str, paper_id: str) -> list[dict]:
    raw_sentences = _extract_candidate_sentences(text)
    claims: list[dict] = []

    for sentence in raw_sentences:
        candidate = _normalize_sentence(sentence)
        if len(candidate) < 20:
            continue

        predicate, keyword = _detect_predicate(candidate.lower())
        if predicate is None:
            continue

        subject_text, object_text, context = _parse_claim_parts(candidate, keyword)
        claims.append(
            {
                "text": candidate,
                "subject_concept_id": None,
                "predicate": predicate,
                "object_concept_id": None,
                "object_text": object_text,
                "context": {
                    "paper_id": paper_id,
                    "subject_text": subject_text,
                    **context,
                },
                "evidence": {"paper_id": paper_id, "extraction": "heuristic"},
                "confidence": 0.55,
            }
        )

    return claims


def _extract_candidate_sentences(text: str) -> list[str]:
    normalized_text = " ".join(text.split())
    if not normalized_text:
        return []
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", normalized_text) if sentence.strip()]


def _normalize_sentence(sentence: str) -> str:
    normalized = " ".join(sentence.split()).strip()
    normalized = re.sub(
        r"^(our|we|this paper|the authors|experiments|results|our experiments|our results)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"^(show|show that|demonstrate|demonstrate that)\s+", "", normalized, flags=re.IGNORECASE)
    return normalized.strip()


def _detect_predicate(sentence: str) -> tuple[str | None, str | None]:
    for keyword, predicate in PREDICATE_PATTERNS:
        if keyword in sentence:
            return predicate, keyword
    if "show" in sentence or "demonstrate" in sentence:
        return "supports", "show"
    return None, None


def _parse_claim_parts(sentence: str, keyword: str | None) -> tuple[str | None, str | None, dict]:
    if not keyword:
        return None, None, {}

    before, after = sentence, ""
    if keyword in sentence.lower():
        match = re.search(re.escape(keyword), sentence, flags=re.IGNORECASE)
        if match:
            before = sentence[: match.start()]
            after = sentence[match.end() :]

    subject_text = _clean_phrase(before)
    object_text = _clean_phrase(after)
    context = {}

    for label, pattern in (
        ("dataset", r"\bon\s+([A-Z][A-Za-z0-9\-]+)\b"),
        ("task", r"\bfor\s+([a-z][a-z0-9\- ]+)$"),
        ("domain", r"\bin\s+([a-z][a-z0-9\- ]+)$"),
    ):
        match = re.search(pattern, object_text or "", flags=re.IGNORECASE)
        if match:
            context[label] = match.group(1).strip()
            object_text = _clean_phrase((object_text or "").replace(match.group(0), ""))

    return subject_text, object_text, context


def _clean_phrase(value: str) -> str | None:
    cleaned = " ".join(value.replace("\n", " ").split()).strip(" .,:;()[]{}")
    cleaned = re.sub(
        r"^(that|the|a|an|our|this|these|those|result|results|experiment|experiments)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(show|shows|demonstrate|demonstrates)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned or None
