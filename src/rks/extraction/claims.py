from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from rks.config import AppPaths
from rks.concepts import link_claims_for_paper
from rks.storage import ClaimRepository, ConceptRepository, EdgeRepository, PaperRepository


CLAIM_EXTRACTOR_VERSION = "1.0"

PREDICATE_PATTERNS = [
    (r"\boutperform(?:s|ed|ing)?\b", "outperforms"),
    (r"\bimprov(?:e|es|ed|ing)\b", "improves"),
    (r"\breduc(?:e|es|ed|ing)\b", "reduces"),
    (r"\bincreas(?:e|es|ed|ing)\b", "increases"),
    (r"\benabl(?:e|es|ed|ing)\b", "enables"),
    (r"\brequir(?:e|es|ed|ing)\b", "requires"),
    (r"\bsupport(?:s|ed|ing)?\b", "supports"),
    (r"\breplac(?:e|es|ed|ing)\b", "replaces"),
    (r"\brefin(?:e|es|ed|ing)\b", "refines"),
    (r"\bextend(?:s|ed|ing)?\b", "extends"),
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
    sections_payload = _load_sections_payload(Path(artifact.path))
    claim_candidates = _extract_candidate_entries(payload=payload, sections_payload=sections_payload)
    normalized_claims = [
        {"text": _normalize_sentence(candidate["text"]), "section": candidate["section"]}
        for candidate in claim_candidates
    ]
    claims = _extract_claim_dicts(claim_candidates=claim_candidates, paper_id=paper_id)
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
        metadata={"count": len(claims), "extractor": extractor, "extractor_version": CLAIM_EXTRACTOR_VERSION},
    )

    stored_claims = claim_repo.replace_claims_for_paper(
        paper_id,
        claims,
        created_by=f"system:{extractor}",
    )
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


def _extract_claim_dicts(claim_candidates: list[dict], paper_id: str) -> list[dict]:
    claims: list[dict] = []

    for candidate_entry in claim_candidates:
        candidate = _normalize_sentence(candidate_entry["text"])
        if len(candidate) < 20:
            continue

        predicate, keyword = _detect_predicate(candidate)
        if predicate is None:
            continue

        subject_text, object_text, context = _parse_claim_parts(candidate, keyword)
        if subject_text is None and object_text is None:
            continue
        evidence = _normalized_evidence(candidate_entry, paper_id)
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
                    "section": candidate_entry["section"],
                    "claim_key": _claim_key(candidate),
                    **context,
                },
                "evidence": evidence,
                "confidence": 0.62 if subject_text and object_text else 0.55,
            }
        )

    return claims


def _extract_candidate_sentences(text: str, base_offset: int) -> list[dict]:
    entries: list[dict] = []
    for sentence_index, match in enumerate(re.finditer(r"[^.!?]+[.!?]?", text, flags=re.DOTALL)):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        leading_space = len(match.group(0)) - len(match.group(0).lstrip())
        sentence_start = base_offset + match.start() + leading_space
        entries.append(
            {
                "text": sentence,
                "char_start": sentence_start,
                "char_end": sentence_start + len(sentence),
                "sentence_index": sentence_index,
            }
        )
    return entries


def _extract_candidate_entries(payload: dict, sections_payload: dict | None) -> list[dict]:
    paragraph_records = {
        int(record["index"]): record for record in payload.get("paragraph_records", [])
    }
    if sections_payload and sections_payload.get("sections"):
        entries = []
        for section in sections_payload["sections"]:
            section_name = section.get("name", "unknown")
            if section_name not in {"abstract", "introduction", "method", "experiments", "results", "conclusion"}:
                continue
            paragraph_indexes = section.get("paragraph_indexes", [])
            for paragraph_index in paragraph_indexes:
                record = paragraph_records.get(int(paragraph_index))
                if record is None:
                    continue
                for sentence in _extract_candidate_sentences(record["text"], int(record["char_start"])):
                    entries.append(
                        {
                            **sentence,
                            "section": section_name,
                            "paragraph_index": record["index"],
                        }
                    )
        if entries:
            return entries

    if payload.get("paragraph_records"):
        entries = []
        for record in payload["paragraph_records"]:
            for sentence in _extract_candidate_sentences(record["text"], int(record["char_start"])):
                entries.append({**sentence, "section": "abstract", "paragraph_index": record["index"]})
        return entries

    return [
        {
            **sentence,
            "section": "abstract",
            "paragraph_index": 0,
        }
        for sentence in _extract_candidate_sentences(payload.get("text", ""), 0)
    ]


def _load_sections_payload(text_artifact_path: Path) -> dict | None:
    sections_path = text_artifact_path.parent / "sections.json"
    if not sections_path.exists():
        return None
    return json.loads(sections_path.read_text(encoding="utf-8"))


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
    for pattern, predicate in PREDICATE_PATTERNS:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if match:
            return predicate, match.group(0)
    lowered = sentence.lower()
    if "show" in lowered or "demonstrate" in lowered:
        return "supports", "show"
    return None, None


def _parse_claim_parts(sentence: str, keyword: str | None) -> tuple[str | None, str | None, dict]:
    if not keyword:
        return None, None, {}

    before, after = sentence, ""
    if keyword.lower() in sentence.lower():
        match = re.search(re.escape(keyword), sentence, flags=re.IGNORECASE)
        if match:
            before = sentence[: match.start()]
            after = sentence[match.end() :]

    subject_text = _clean_phrase(before)
    object_text = _clean_phrase(after)
    context = {}

    for label, pattern in (
        ("dataset", r"\bon\s+([A-Z][A-Za-z0-9.\-]*(?:\s+[A-Z0-9][A-Za-z0-9.\-]*)*)"),
        ("task", r"\bfor\s+([a-z][a-z0-9\- ]+?)(?:\s+(?:on|in|with)\b|$)"),
        ("domain", r"\bin\s+([a-z][a-z0-9\- ]+?)(?:\s+(?:with|using)\b|$)"),
    ):
        match = re.search(pattern, object_text or "", flags=re.IGNORECASE)
        if match:
            context[label] = match.group(1).strip()
            object_text = _clean_phrase((object_text or "").replace(match.group(0), ""))

    if subject_text is None:
        leading_subject = re.match(r"^([A-Z][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9\-]+){0,4})", sentence)
        if leading_subject:
            subject_text = _clean_phrase(leading_subject.group(1))

    if object_text is None and subject_text:
        tail = sentence.replace(subject_text, "", 1)
        if keyword:
            keyword_match = re.search(re.escape(keyword), tail, flags=re.IGNORECASE)
            if keyword_match:
                tail = tail[keyword_match.end() :]
        object_text = _clean_phrase(tail)

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
    cleaned = re.sub(r"\b(better|more|less)\s+than\b.*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned or None


def _normalized_evidence(candidate_entry: dict, paper_id: str) -> dict:
    return {
        "paper_id": paper_id,
        "extraction": "heuristic",
        "extractor_version": CLAIM_EXTRACTOR_VERSION,
        "section": candidate_entry["section"],
        "paragraph_index": candidate_entry.get("paragraph_index"),
        "sentence_index": candidate_entry.get("sentence_index"),
        "char_start": candidate_entry.get("char_start"),
        "char_end": candidate_entry.get("char_end"),
        "snippet": candidate_entry["text"],
    }


def _claim_key(sentence: str) -> str:
    return hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:12]
