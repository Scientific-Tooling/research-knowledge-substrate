from __future__ import annotations

import json
import re
from pathlib import Path

from rks.config import AppPaths
from rks.concepts.normalize import canonicalize_term
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    DatasetRepository,
    EdgeRepository,
    MethodRepository,
    PaperRepository,
)


METHOD_EXTRACTOR_VERSION = "1.0"
DATASET_EXTRACTOR_VERSION = "1.0"
CITATION_EXTRACTOR_VERSION = "1.0"

_METHOD_PATTERNS = [
    re.compile(
        r"\b(?:we|this paper|our work)\s+(?:propose|present|introduce|develop|design|build|create)\s+([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:our|the proposed|a novel)\s+(?:method|approach|framework|algorithm|architecture|model)\s*,?\s+([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})",
        flags=re.IGNORECASE,
    ),
]
_DATASET_PATTERN = re.compile(
    r"\bon\s+([A-Z][A-Za-z0-9.\-]*(?:\s+[A-Z0-9][A-Za-z0-9.\-]*)*)",
    flags=re.IGNORECASE,
)


def extract_methods_for_paper(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    method_repo: MethodRepository,
    dataset_repo: DatasetRepository,
    paper_id: str,
) -> list:
    text_payload = _load_text_payload(paper_repo, paper_id)
    claims = claim_repo.list_claims_for_paper(paper_id)
    candidates: dict[str, dict] = {}

    for paragraph in text_payload.get("paragraph_records", []):
        text = paragraph["text"]
        for pattern in _METHOD_PATTERNS:
            match = pattern.search(text)
            if match:
                _remember_method_candidate(candidates, match.group(1), text)

    for claim in claims:
        context = json.loads(claim.context_json or "{}")
        subject_text = context.get("subject_text")
        section = context.get("section")
        if subject_text and section in {"abstract", "introduction", "method"} and _looks_like_method_name(subject_text):
            _remember_method_candidate(candidates, subject_text, claim.text)

    methods = []
    for candidate in candidates.values():
        concept = concept_repo.get_or_create(candidate["name"])
        methods.append(
            {
                "name": candidate["name"],
                "description": candidate["description"],
                "about_concept_id": concept.id,
            }
        )

    stored_methods = method_repo.replace_methods_for_paper(paper_id, methods)
    _write_artifact(
        paper_repo,
        paths,
        paper_id,
        "methods",
        "methods.json",
        methods,
        {"count": len(methods), "extractor": "regex", "extractor_version": METHOD_EXTRACTOR_VERSION},
    )
    _rebuild_research_object_edges(
        claim_repo=claim_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        methods=stored_methods,
        datasets=dataset_repo.list_datasets_for_paper(paper_id),
    )
    return stored_methods


def extract_methods_with_llm(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    method_repo: MethodRepository,
    dataset_repo: DatasetRepository,
    paper_id: str,
    provider,
) -> list:
    text_payload = _load_text_payload(paper_repo, paper_id)
    if not text_payload:
        return []
    raw_methods = provider.parse_methods(text_payload)
    methods = []
    for m in raw_methods:
        concept = concept_repo.get_or_create(m["name"])
        methods.append(
            {
                "name": m["name"],
                "description": m.get("description") or "",
                "about_concept_id": concept.id,
            }
        )
    stored_methods = method_repo.replace_methods_for_paper(paper_id, methods)
    _write_artifact(
        paper_repo,
        paths,
        paper_id,
        "methods",
        "methods.json",
        methods,
        {"count": len(methods), "extractor": "llm_api", "extractor_version": METHOD_EXTRACTOR_VERSION},
    )
    _rebuild_research_object_edges(
        claim_repo=claim_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        methods=stored_methods,
        datasets=dataset_repo.list_datasets_for_paper(paper_id),
    )
    return stored_methods


def extract_datasets_for_paper(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    edge_repo: EdgeRepository,
    dataset_repo: DatasetRepository,
    method_repo: MethodRepository,
    paper_id: str,
) -> list:
    text_payload = _load_text_payload(paper_repo, paper_id)
    claims = claim_repo.list_claims_for_paper(paper_id)
    candidates: dict[str, dict] = {}

    for claim in claims:
        context = json.loads(claim.context_json or "{}")
        dataset_name = context.get("dataset")
        if dataset_name:
            _remember_dataset_candidate(candidates, dataset_name, claim.text)
        for match in _DATASET_PATTERN.finditer(claim.text):
            _remember_dataset_candidate(candidates, match.group(1), claim.text)

    for paragraph in text_payload.get("paragraph_records", []):
        for match in _DATASET_PATTERN.finditer(paragraph["text"]):
            _remember_dataset_candidate(candidates, match.group(1), paragraph["text"])

    datasets = [
        {
            "name": candidate["name"],
            "description": candidate["description"],
            "source": "regex",
        }
        for candidate in candidates.values()
    ]
    stored_datasets = dataset_repo.replace_datasets_for_paper(paper_id, datasets)
    _write_artifact(
        paper_repo,
        paths,
        paper_id,
        "datasets",
        "datasets.json",
        datasets,
        {"count": len(datasets), "extractor": "regex", "extractor_version": DATASET_EXTRACTOR_VERSION},
    )
    _rebuild_research_object_edges(
        claim_repo=claim_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        methods=method_repo.list_methods_for_paper(paper_id),
        datasets=stored_datasets,
    )
    return stored_datasets


def extract_datasets_with_llm(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    edge_repo: EdgeRepository,
    dataset_repo: DatasetRepository,
    method_repo: MethodRepository,
    paper_id: str,
    provider,
) -> list:
    text_payload = _load_text_payload(paper_repo, paper_id)
    if not text_payload:
        return []
    raw_datasets = provider.parse_datasets(text_payload)
    datasets = [
        {
            "name": d["name"],
            "description": d.get("description") or "",
            "source": d.get("source") or None,
        }
        for d in raw_datasets
    ]
    stored_datasets = dataset_repo.replace_datasets_for_paper(paper_id, datasets)
    _write_artifact(
        paper_repo,
        paths,
        paper_id,
        "datasets",
        "datasets.json",
        datasets,
        {"count": len(datasets), "extractor": "llm_api", "extractor_version": DATASET_EXTRACTOR_VERSION},
    )
    _rebuild_research_object_edges(
        claim_repo=claim_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        methods=method_repo.list_methods_for_paper(paper_id),
        datasets=stored_datasets,
    )
    return stored_datasets


def extract_all_with_llm(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    method_repo: MethodRepository,
    dataset_repo: DatasetRepository,
    paper_id: str,
    provider,
) -> dict:
    """Single-pass combined extraction (paper.v1) for *paper_id*.

    Calls ``provider.extract_all()`` once with the raw text source, then
    persists text, claims, methods, datasets, and summary in sequence.
    Returns a dict with item counts per stage.
    """
    from rks.extraction.claims import persist_claims_for_paper
    from rks.extraction.text import build_text_source_input, write_text_artifact
    from rks.reasoning.summary import persist_summary_artifact

    paper = paper_repo.get_paper(paper_id)
    text_source = build_text_source_input(paper)
    result = provider.extract_all(text_source)

    # 1. text
    text_payload = {
        "text": result["text"],
        "paragraphs": result.get("paragraphs", []),
        "warnings": result.get("warnings", []),
        "extractor": "llm_api",
        "extraction_mode": "llm-api-combined",
    }
    write_text_artifact(repo=paper_repo, paths=paths, paper_id=paper_id, payload=text_payload)

    # 2. claims
    stored_claims = persist_claims_for_paper(
        paths=paths,
        paper_repo=paper_repo,
        claim_repo=claim_repo,
        concept_repo=concept_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        claims=result.get("claims", []),
        extractor="llm_api",
    )

    # 3. methods
    methods = []
    for m in result.get("methods", []):
        concept = concept_repo.get_or_create(m["name"])
        methods.append({
            "name": m["name"],
            "description": m.get("description") or "",
            "about_concept_id": concept.id,
        })
    stored_methods = method_repo.replace_methods_for_paper(paper_id, methods)
    _write_artifact(
        paper_repo, paths, paper_id, "methods", "methods.json", methods,
        {"count": len(methods), "extractor": "llm_api", "extractor_version": METHOD_EXTRACTOR_VERSION},
    )

    # 4. datasets
    datasets = []
    for d in result.get("datasets", []):
        datasets.append({
            "name": d["name"],
            "description": d.get("description") or "",
            "source": d.get("source") or None,
        })
    stored_datasets = dataset_repo.replace_datasets_for_paper(paper_id, datasets)
    _write_artifact(
        paper_repo, paths, paper_id, "datasets", "datasets.json", datasets,
        {"count": len(datasets), "extractor": "llm_api", "extractor_version": DATASET_EXTRACTOR_VERSION},
    )

    _rebuild_research_object_edges(
        claim_repo=claim_repo,
        edge_repo=edge_repo,
        paper_id=paper_id,
        methods=stored_methods,
        datasets=stored_datasets,
    )

    # 5. summary
    summary_payload = {
        "summary": result.get("summary", ""),
        "evidence_claim_ids": result.get("evidence_claim_ids", []),
        "evidence_paper_ids": result.get("evidence_paper_ids", [paper_id]),
        "citations": result.get("citations", []),
        "open_questions": result.get("open_questions", []),
        "mode": "llm-api-combined",
    }
    persist_summary_artifact(
        paper_repo=paper_repo,
        paths=paths,
        paper_id=paper_id,
        payload=summary_payload,
        artifact_type="paper_summary",
        filename="paper_summary.json",
    )

    return {
        "text": 1,
        "claims": len(stored_claims),
        "methods": len(stored_methods),
        "datasets": len(stored_datasets),
        "summary": 1,
    }


def persist_citations_for_paper(
    paths: AppPaths,
    paper_repo: PaperRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
    citations: list[dict],
) -> list[dict]:
    normalized_citations = [_normalize_citation(citation) for citation in citations]
    normalized_citations = [citation for citation in normalized_citations if citation["title"] or citation["doi"]]

    edge_repo.clear_edges_for_paper_relations(paper_id, ["cites"])
    stored: list[dict] = []
    for citation in normalized_citations:
        target = _resolve_citation_target(paper_repo, citation)
        target_paper_id = target.id if target is not None else None
        if target is not None:
            edge_repo.create_edge(
                source_id=paper_id,
                source_type="paper",
                relation_type="cites",
                target_id=target.id,
                target_type="paper",
                evidence_paper_id=paper_id,
                confidence=0.75,
                metadata={"doi": citation.get("doi"), "title": citation.get("title")},
            )
        stored.append({"target_paper_id": target_paper_id, **citation})

    _write_artifact(
        paper_repo,
        paths,
        paper_id,
        "citations",
        "citations.json",
        stored,
        {"count": len(stored), "extractor": "metadata", "extractor_version": CITATION_EXTRACTOR_VERSION},
    )
    return stored


def _load_text_payload(paper_repo: PaperRepository, paper_id: str) -> dict:
    paper = paper_repo.get_paper(paper_id)
    if not paper.text_artifact_id:
        return {}
    artifact = paper_repo.get_artifact(paper.text_artifact_id)
    return json.loads(Path(artifact.path).read_text(encoding="utf-8"))


def _remember_method_candidate(candidates: dict[str, dict], raw_name: str, description: str) -> None:
    name = canonicalize_term(raw_name)
    if not _looks_like_method_name(name):
        return
    candidates.setdefault(name, {"name": name, "description": description})


def _remember_dataset_candidate(candidates: dict[str, dict], raw_name: str, description: str) -> None:
    name = canonicalize_term(raw_name.rstrip(".,;:"))
    if not _looks_like_dataset_name(name):
        return
    candidates.setdefault(name, {"name": name, "description": description})


_METHOD_STOPWORDS = {
    "paper", "result", "results", "experiment", "experiments",
    "section", "table", "figure", "we", "our", "this", "the",
    "it", "they", "there", "here", "that", "which",
}

_METHOD_SIGNAL_TOKENS = {
    "attention", "transformer", "model", "network", "system",
    "encoder", "decoder", "architecture", "layer", "module",
    "optimizer", "scheduler", "loss", "regulariz", "algorithm",
    "framework", "pipeline", "agent", "classifier", "detector",
}


def _looks_like_method_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in _METHOD_STOPWORDS:
        return False
    tokens = name.split()
    if len(tokens) > 6:
        return False
    # Accept if: has uppercase char, or contains a known signal token, or has a hyphen (e.g. "BERT-large")
    has_upper = any(char.isupper() for char in name)
    has_signal = any(sig in lowered for sig in _METHOD_SIGNAL_TOKENS)
    has_hyphen = "-" in name
    return has_upper or has_signal or has_hyphen


_DATASET_STOPWORDS = {
    "result", "results", "table", "figure", "method", "methods",
    "section", "paper", "approach", "model", "experiment",
}

_KNOWN_DATASETS = {
    "ImageNet", "CIFAR-10", "CIFAR-100", "WMT14", "WMT16",
    "GLUE", "SuperGLUE", "SQuAD", "MNLI", "COCO", "Pascal VOC",
    "Penn Treebank", "WikiText", "OpenWebText", "Common Crawl",
}


def _looks_like_dataset_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in _DATASET_STOPWORDS:
        return False
    if name in _KNOWN_DATASETS:
        return True
    # Accept if: has digit, is all-uppercase, has mixed case with capital start,
    # or contains a hyphen/dot suggesting a versioned name
    has_digit = any(char.isdigit() for char in name)
    is_upper = name.isupper() and len(name) >= 2
    has_version_marker = bool(re.search(r"[-.]", name)) and any(char.isupper() for char in name)
    has_mixed_case = name[0].isupper() and any(char.islower() for char in name) and len(name) >= 3
    return has_digit or is_upper or has_version_marker or has_mixed_case


def _write_artifact(
    paper_repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    artifact_type: str,
    filename: str,
    payload,
    metadata: dict,
) -> None:
    paper_dir = Path(paths.papers_dir / paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    output_path = paper_dir / filename
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paper_repo.create_artifact(
        paper_id=paper_id,
        artifact_type=artifact_type,
        path=output_path,
        format_name="json",
        metadata=metadata,
    )


def _rebuild_research_object_edges(
    claim_repo: ClaimRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
    methods: list,
    datasets: list,
) -> None:
    edge_repo.clear_edges_for_paper_relations(paper_id, ["proposes", "uses", "evaluated_on"])

    for method in methods:
        edge_repo.create_edge(
            source_id=paper_id,
            source_type="paper",
            relation_type="proposes",
            target_id=method.id,
            target_type="method",
            evidence_paper_id=paper_id,
            confidence=0.7,
            metadata={"name": method.name},
        )

    for dataset in datasets:
        edge_repo.create_edge(
            source_id=paper_id,
            source_type="paper",
            relation_type="uses",
            target_id=dataset.id,
            target_type="dataset",
            evidence_paper_id=paper_id,
            confidence=0.72,
            metadata={"name": dataset.name},
        )

    claims = claim_repo.list_claims_for_paper(paper_id)
    method_map = {canonicalize_term(method.name): method for method in methods}
    dataset_map = {canonicalize_term(dataset.name): dataset for dataset in datasets}
    linked_pairs: set[tuple[str, str]] = set()

    for claim in claims:
        context = json.loads(claim.context_json or "{}")
        subject_text = canonicalize_term(context.get("subject_text", "")) if context.get("subject_text") else ""
        dataset_text = canonicalize_term(context.get("dataset", "")) if context.get("dataset") else ""
        method = method_map.get(subject_text)
        dataset = dataset_map.get(dataset_text)
        if method is None or dataset is None:
            continue
        linked_pairs.add((method.id, dataset.id))
        edge_repo.create_edge(
            source_id=method.id,
            source_type="method",
            relation_type="evaluated_on",
            target_id=dataset.id,
            target_type="dataset",
            evidence_paper_id=paper_id,
            confidence=claim.confidence,
            metadata={"claim_id": claim.id},
        )

    # Note: removed forced single-method/single-dataset fallback edge
    # that created false positives. Method-dataset links now require
    # claim-level evidence only.


def _normalize_citation(citation: dict) -> dict:
    return {
        "title": (citation.get("title") or citation.get("article-title") or citation.get("unstructured") or "").strip(),
        "doi": (citation.get("doi") or citation.get("DOI") or "").strip() or None,
        "year": citation.get("year"),
    }


def _resolve_citation_target(paper_repo: PaperRepository, citation: dict):
    """Return an existing paper matching this citation, or None if not yet ingested."""
    if citation.get("doi"):
        existing = paper_repo.find_by_doi(citation["doi"])
        if existing is not None:
            return existing
    if citation.get("title"):
        existing = paper_repo.find_by_title(citation["title"])
        if existing is not None:
            return existing
    return None
