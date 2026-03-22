from __future__ import annotations


DUAL_TRACK_SPEC_VERSION = "v1"
ALL_EXTRACTION_MODES = ("llm-api", "agent")

TEXT_SCHEMA_VERSION = "text.v1"
CLAIMS_SCHEMA_VERSION = "claims.v3"
METHODS_SCHEMA_VERSION = "methods.v1"
DATASETS_SCHEMA_VERSION = "datasets.v1"
SUMMARY_SCHEMA_VERSION = "summary.v1"
PAPER_SCHEMA_VERSION = "paper.v1"


def build_dual_track_request(
    *,
    task: str,
    paper_id: str,
    instruction: str,
    input_payload: dict,
    expected_output_schema: dict,
    schema_version: str,
) -> dict:
    return {
        "spec_version": DUAL_TRACK_SPEC_VERSION,
        "schema_version": schema_version,
        "task": task,
        "paper_id": paper_id,
        "instruction": instruction,
        "input": input_payload,
        "expected_output_schema": expected_output_schema,
    }


def validate_text_result_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Text result must be a JSON object.")

    for required_key in ("text", "paragraphs", "warnings"):
        if required_key not in payload:
            raise ValueError(f"Text result is missing required key: {required_key}")

    if not isinstance(payload["paragraphs"], list):
        raise ValueError("Text result `paragraphs` must be a list.")
    if not isinstance(payload["warnings"], list):
        raise ValueError("Text result `warnings` must be a list.")
    return payload


_VALID_CLAIM_SECTIONS = {"abstract", "introduction", "method", "experiments", "results", "conclusion", "discussion"}


def validate_claims_result_payload(payload) -> list[dict]:
    """Validate a claims extraction result (claims.v1, claims.v2, and claims.v3).

    Required per claim: text, predicate, context (with subject_text), evidence, confidence.
    Optional (claims.v2): context.section, context.dataset, evidence.quote.
    Optional (claims.v3): top-level concept_aliases list — each entry needs canonical (str)
        and aliases (list of str). Used to reduce concept fragmentation at import time.
    """
    claims = payload.get("claims") if isinstance(payload, dict) else payload
    if not isinstance(claims, list):
        raise ValueError("Claims result must be a list or an object with top-level `claims`.")

    required_keys = {"text", "predicate", "context", "evidence", "confidence"}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise ValueError(f"Claim at index {index} must be an object.")
        missing = sorted(required_keys - set(claim))
        if missing:
            raise ValueError(f"Claim at index {index} is missing required keys: {', '.join(missing)}")
        if not isinstance(claim["context"], dict):
            raise ValueError(f"Claim at index {index} has a non-object `context`.")
        if "subject_text" not in claim["context"]:
            raise ValueError(f"Claim at index {index} is missing `context.subject_text`.")
        if not isinstance(claim["evidence"], dict):
            raise ValueError(f"Claim at index {index} has a non-object `evidence`.")
        # Optional v2 fields — validate type when present
        section = claim["context"].get("section")
        if section is not None and section not in _VALID_CLAIM_SECTIONS:
            raise ValueError(
                f"Claim at index {index} has invalid `context.section` '{section}'; "
                f"must be one of: {', '.join(sorted(_VALID_CLAIM_SECTIONS))}."
            )
        dataset = claim["context"].get("dataset")
        if dataset is not None and not isinstance(dataset, str):
            raise ValueError(f"Claim at index {index} has a non-string `context.dataset`.")
        quote = claim["evidence"].get("quote")
        if quote is not None and not isinstance(quote, str):
            raise ValueError(f"Claim at index {index} has a non-string `evidence.quote`.")

    # Optional v3 field: concept_aliases
    if isinstance(payload, dict) and "concept_aliases" in payload:
        concept_aliases = payload["concept_aliases"]
        if not isinstance(concept_aliases, list):
            raise ValueError("concept_aliases must be a list.")
        for idx, entry in enumerate(concept_aliases):
            if not isinstance(entry, dict):
                raise ValueError(f"concept_aliases entry at index {idx} must be an object.")
            if "canonical" not in entry or not isinstance(entry["canonical"], str):
                raise ValueError(f"concept_aliases entry at index {idx} is missing a string `canonical`.")
            if "aliases" not in entry or not isinstance(entry["aliases"], list):
                raise ValueError(f"concept_aliases entry at index {idx} is missing a list `aliases`.")
            for alias in entry["aliases"]:
                if not isinstance(alias, str):
                    raise ValueError(f"concept_aliases entry at index {idx} has a non-string alias.")

    return claims


def validate_summary_result_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Summary result must be a JSON object.")
    if "summary" not in payload:
        raise ValueError("Summary result is missing required key: summary")
    if not isinstance(payload["summary"], str):
        raise ValueError("Summary result `summary` must be a string.")
    if "evidence_claim_ids" in payload and not isinstance(payload["evidence_claim_ids"], list):
        raise ValueError("Summary result `evidence_claim_ids` must be a list when present.")
    if "open_questions" in payload and not isinstance(payload["open_questions"], list):
        raise ValueError("Summary result `open_questions` must be a list when present.")
    return payload


def validate_methods_result_payload(payload) -> list[dict]:
    """Validate a methods extraction result.

    Accepts either a bare list or ``{"methods": [...]}``."""
    methods = payload.get("methods") if isinstance(payload, dict) else payload
    if not isinstance(methods, list):
        raise ValueError("Methods result must be a list or an object with top-level `methods`.")
    for index, method in enumerate(methods):
        if not isinstance(method, dict):
            raise ValueError(f"Method at index {index} must be an object.")
        if "name" not in method or not isinstance(method["name"], str) or not method["name"].strip():
            raise ValueError(f"Method at index {index} is missing a non-empty `name`.")
        if "description" in method and not isinstance(method["description"], str):
            raise ValueError(f"Method at index {index} has a non-string `description`.")
        if "proposed_by_this_paper" in method and not isinstance(method["proposed_by_this_paper"], bool):
            raise ValueError(f"Method at index {index} has a non-boolean `proposed_by_this_paper`.")
        if "aliases" in method and not isinstance(method["aliases"], list):
            raise ValueError(f"Method at index {index} has a non-list `aliases`.")
    return methods


def validate_datasets_result_payload(payload) -> list[dict]:
    """Validate a datasets extraction result.

    Accepts either a bare list or ``{"datasets": [...]}``."""
    datasets = payload.get("datasets") if isinstance(payload, dict) else payload
    if not isinstance(datasets, list):
        raise ValueError("Datasets result must be a list or an object with top-level `datasets`.")
    for index, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            raise ValueError(f"Dataset at index {index} must be an object.")
        if "name" not in dataset or not isinstance(dataset["name"], str) or not dataset["name"].strip():
            raise ValueError(f"Dataset at index {index} is missing a non-empty `name`.")
        if "description" in dataset and dataset["description"] is not None and not isinstance(dataset["description"], str):
            raise ValueError(f"Dataset at index {index} has a non-string `description`.")
        if "source" in dataset and dataset["source"] is not None and not isinstance(dataset["source"], str):
            raise ValueError(f"Dataset at index {index} has a non-string `source`.")
        if "used_for" in dataset and dataset["used_for"] is not None:
            valid_used_for = {"train", "eval", "both"}
            if dataset["used_for"] not in valid_used_for:
                raise ValueError(
                    f"Dataset at index {index} has invalid `used_for` value '{dataset['used_for']}'; "
                    f"must be one of: {', '.join(sorted(valid_used_for))}."
                )
    return datasets


def validate_paper_result_payload(payload: dict) -> dict:
    """Validate a combined paper extraction result (paper.v1).

    Contains text, claims, methods, datasets, and summary in one payload.
    All sub-components are validated using their respective validators.
    """
    if not isinstance(payload, dict):
        raise ValueError("Paper result must be a JSON object.")
    for key in ("text", "paragraphs", "warnings", "claims", "methods", "datasets", "summary"):
        if key not in payload:
            raise ValueError(f"Paper result is missing required key: {key}")
    if not isinstance(payload["paragraphs"], list):
        raise ValueError("Paper result `paragraphs` must be a list.")
    if not isinstance(payload["warnings"], list):
        raise ValueError("Paper result `warnings` must be a list.")
    validate_claims_result_payload({"claims": payload["claims"]})
    validate_methods_result_payload({"methods": payload["methods"]})
    validate_datasets_result_payload({"datasets": payload["datasets"]})
    if not isinstance(payload["summary"], str):
        raise ValueError("Paper result `summary` must be a string.")
    return payload
