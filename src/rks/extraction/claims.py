from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from rks.config import AppPaths
from rks.concepts import link_claims_for_paper
from rks.storage import ClaimRepository, ConceptRepository, EdgeRepository, PaperRepository


CLAIM_EXTRACTOR_VERSION = "1.1"

PREDICATE_PATTERNS = [
    # Comparative / performance
    (r"\boutperform(?:s|ed|ing)?\b", "outperforms"),
    (r"\bsurpass(?:es|ed|ing)?\b", "outperforms"),
    (r"\bexceed(?:s|ed|ing)?\b", "outperforms"),
    (r"\bimprov(?:e|es|ed|ing)\b", "improves"),
    (r"\breduc(?:e|es|ed|ing)\b", "reduces"),
    (r"\bincreas(?:e|es|ed|ing)\b", "increases"),
    # Capability / dependency
    (r"\benabl(?:e|es|ed|ing)\b", "enables"),
    (r"\bfacilit(?:ate|ates|ated|ating)\b", "enables"),
    (r"\brequir(?:e|es|ed|ing)\b", "requires"),
    (r"\brely\b|\breli(?:es|ed|ing)\b", "requires"),
    # Evidence / validation
    (r"\bsupport(?:s|ed|ing)?\b", "supports"),
    (r"\bvalidat(?:e|es|ed|ing)\b", "supports"),
    (r"\bconfirm(?:s|ed|ing)?\b", "supports"),
    (r"\bcorroborat(?:e|es|ed|ing)\b", "supports"),
    # Structural
    (r"\breplac(?:e|es|ed|ing)\b", "replaces"),
    (r"\brefin(?:e|es|ed|ing)\b", "refines"),
    (r"\bextend(?:s|ed|ing)?\b", "extends"),
    (r"\bgeneraliz(?:e|es|ed|ing)\b", "extends"),
    # Achievement / result
    (r"\bachiev(?:e|es|ed|ing)\b", "achieves"),
    (r"\battain(?:s|ed|ing)?\b", "achieves"),
    # Scalability / robustness
    (r"\bscal(?:e|es|ed|ing)\b", "scales"),
    (r"\bconverg(?:e|es|ed|ing)\b", "converges"),
    # Negative / limitation
    (r"\bdegrad(?:e|es|ed|ing)\b", "degrades"),
    (r"\blimit(?:s|ed|ing)?\b", "limits"),
    (r"\bfail(?:s|ed|ing)?\b", "fails"),
    # Correlation / association
    (r"\bcorrelat(?:e|es|ed|ing)\b", "correlates"),
    (r"\baddress(?:es|ed|ing)?\b", "addresses"),
    (r"\bmitigat(?:e|es|ed|ing)\b", "mitigates"),
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
        extractor="regex",
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
        metadata={
            "count": len(claims),
            "extractor": extractor,
            "extractor_version": CLAIM_EXTRACTOR_VERSION,
            "schema_version": _claims_schema_version(claims),
        },
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


_ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "vs", "etc", "inc", "ltd",
    "fig", "figs", "eq", "eqs", "ref", "refs", "vol", "no", "approx",
    "al", "et", "dept", "univ", "assoc", "conf", "proc", "trans",
    "i", "ii", "iii", "iv", "ed", "eds", "ch", "sec", "pp",
}

# Multi-letter dot-separated acronyms like "U.S.", "i.e.", "e.g."
_ACRONYM_PATTERN = re.compile(r"\b([A-Za-z]\.){2,}$")

_SENTENCE_BOUNDARY = re.compile(
    r"""
    (?<=[.!?])          # lookbehind: sentence-ending punctuation
    (?<![A-Z][.])       # not a single capital + dot (initials like "J.")
    \s+                 # whitespace gap
    (?=[A-Z"\(a-z])     # lookahead: next sentence starts with any letter, quote, or paren
    """,
    re.VERBOSE,
)


def _extract_candidate_sentences(text: str, base_offset: int) -> list[dict]:
    entries: list[dict] = []
    parts = _SENTENCE_BOUNDARY.split(text)
    offset = 0
    pending_prefix = ""
    pending_offset = 0
    output_index = 0
    for part_index, raw in enumerate(parts):
        pos = text.find(raw, offset)
        if pos == -1:
            pos = offset
        sentence = raw.strip()
        if not sentence:
            offset = pos + len(raw)
            continue
        # Rejoin with pending abbreviation fragment
        if pending_prefix:
            sentence = pending_prefix + " " + sentence
            pos = pending_offset
            pending_prefix = ""
        # Check if this part ends with an abbreviation or acronym — if so, buffer it
        stripped = sentence.rstrip(".!?")
        last_word = stripped.rsplit(None, 1)[-1].lower() if stripped else ""
        is_abbrev = last_word in _ABBREVIATIONS
        is_acronym = bool(_ACRONYM_PATTERN.search(sentence.rstrip()))
        if (is_abbrev or is_acronym) and part_index < len(parts) - 1:
            pending_prefix = sentence
            pending_offset = pos
            offset = pos + len(raw)
            continue
        leading_space = len(raw) - len(raw.lstrip())
        sentence_start = base_offset + pos + leading_space
        entries.append(
            {
                "text": sentence,
                "char_start": sentence_start,
                "char_end": sentence_start + len(sentence),
                "sentence_index": output_index,
            }
        )
        output_index += 1
        offset = pos + len(raw)
    # Flush any remaining buffered prefix
    if pending_prefix:
        entries.append(
            {
                "text": pending_prefix,
                "char_start": base_offset + pending_offset,
                "char_end": base_offset + pending_offset + len(pending_prefix),
                "sentence_index": output_index,
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
    for _ in range(3):
        prev = normalized
        normalized = re.sub(
            r"^(our|we|this paper|the authors|experiments|results|our experiments|our results)\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"^(show that|demonstrate that|show|demonstrate)\s+", "", normalized, flags=re.IGNORECASE)
        if normalized == prev:
            break
    return normalized.strip()


def _detect_predicate(sentence: str) -> tuple[str | None, str | None]:
    for pattern, predicate in PREDICATE_PATTERNS:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if match:
            return predicate, match.group(0)
    lowered = sentence.lower()
    if "show" in lowered or "demonstrate" in lowered or "indicat" in lowered:
        return "supports", "show"
    if "propos" in lowered or "introduc" in lowered or "present" in lowered:
        return "proposes", "propose"
    return None, None


_PASSIVE_PATTERN = re.compile(
    r"\b(?:is|are|was|were|been)\s+(\w+(?:ed|ing))\s+by\b",
    re.IGNORECASE,
)


def _parse_claim_parts(sentence: str, keyword: str | None) -> tuple[str | None, str | None, dict]:
    if not keyword:
        return None, None, {}

    # Detect passive voice ("X is improved by Y") and swap to active form
    passive_match = _PASSIVE_PATTERN.search(sentence)
    is_passive = passive_match is not None and keyword.lower() in passive_match.group(0).lower()

    before, after = sentence, ""
    if keyword.lower() in sentence.lower():
        match = re.search(re.escape(keyword), sentence, flags=re.IGNORECASE)
        if match:
            before = sentence[: match.start()]
            after = sentence[match.end() :]

    if is_passive and passive_match:
        # In passive voice, the real subject follows the agent-marker "by".
        # Use the last occurrence to avoid matching "by" in phrases like "by 10%".
        by_pos = after.lower().rfind(" by ")
        if by_pos >= 0:
            real_subject = after[by_pos + 4:]
            real_object = before
            # Strip the auxiliary verb ("is", "are", etc.) from the object
            real_object = re.sub(r"\s*\b(?:is|are|was|were|been)\s*$", "", real_object, flags=re.IGNORECASE)
            before = real_subject
            after = real_object

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
    cleaned = re.sub(r"^(shows|show|demonstrates|demonstrate)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned or None


def _normalized_evidence(candidate_entry: dict, paper_id: str) -> dict:
    return {
        "paper_id": paper_id,
        "extraction": "regex",
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


def _claims_schema_version(claims: list[dict]) -> str | None:
    for claim in claims:
        evidence = claim.get("evidence", {})
        if evidence.get("schema_version"):
            return evidence["schema_version"]
    return None
