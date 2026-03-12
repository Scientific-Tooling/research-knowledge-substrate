from __future__ import annotations


DUAL_TRACK_SPEC_VERSION = "v1"
ALL_EXTRACTION_MODES = ("heuristic", "llm-api", "agent")


def build_dual_track_request(
    *,
    task: str,
    paper_id: str,
    instruction: str,
    input_payload: dict,
    expected_output_schema: dict,
) -> dict:
    return {
        "spec_version": DUAL_TRACK_SPEC_VERSION,
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


def validate_claims_result_payload(payload) -> list[dict]:
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
