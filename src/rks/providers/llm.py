from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from rks.config import LlmConfig
from rks.llm import validate_claims_result_payload, validate_summary_result_payload, validate_text_result_payload

_DEFAULT_TIMEOUT = 60
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0
_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB


def _read_pdf_base64(pdf_path: str | None) -> str | None:
    """Read a PDF file and return its base64-encoded content.

    Returns None if the file is missing, unreadable, or exceeds the size limit.
    """
    if not pdf_path:
        return None
    path = Path(pdf_path)
    if not path.exists():
        return None
    if path.stat().st_size > _MAX_PDF_BYTES:
        return None
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None


class OpenAICompatibleLlmProvider:
    def __init__(self, config: LlmConfig, urlopen=urllib.request.urlopen):
        self.config = config
        self.urlopen = urlopen

    def extract_text(self, input_payload: dict) -> dict:
        pdf_base64 = _read_pdf_base64(input_payload.get("source_pdf"))
        prompt = {
            "task": "extract_research_text",
            "instructions": [
                "Return only JSON.",
                "Extract all readable research text from the attached PDF document.",
                "Use the rough_text field as supplementary context only.",
                "Return keys: text, paragraphs, warnings.",
            ] if pdf_base64 else [
                "Return only JSON.",
                "Preserve readable research text.",
                "Return keys: text, paragraphs, warnings.",
            ],
            "input": input_payload,
        }
        response = validate_text_result_payload(
            self._chat_json(prompt, pdf_base64=pdf_base64)
        )
        return {
            "created_at": None,
            "extractor": "llm_api",
            "source_pdf": input_payload.get("source_pdf"),
            "text": response.get("text", ""),
            "paragraphs": response.get("paragraphs", []),
            "warnings": response.get("warnings", []),
        }

    def parse_claims(self, text_payload: dict) -> list[dict]:
        prompt = {
            "task": "extract_structured_claims",
            "instructions": [
                "Return only JSON.",
                "Return a top-level key `claims`.",
                "Each claim must include text, predicate, object_text, context, evidence, confidence.",
                "Put subject_text inside context.subject_text.",
            ],
            "input": text_payload,
        }
        response = self._chat_json(prompt)
        return validate_claims_result_payload(response)

    def summarize_paper(self, summary_input: dict) -> dict:
        prompt = {
            "task": "summarize_paper",
            "instructions": [
                "Return only JSON.",
                "Return keys: summary, evidence_claim_ids, evidence_paper_ids, citations, open_questions.",
                "The summary should be concise and grounded in the input evidence.",
            ],
            "input": summary_input,
        }
        return validate_summary_result_payload(self._chat_json(prompt))

    def _chat_json(self, payload: dict, *, pdf_base64: str | None = None) -> dict:
        text_content = json.dumps(payload)

        if pdf_base64:
            # Multi-part content: PDF document + text prompt.
            # Uses the OpenAI-compatible content array format.
            # Providers that support document input (via proxies like
            # LiteLLM, OpenRouter, etc.) will translate this to their
            # native format automatically.
            user_content: str | list = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:application/pdf;base64,{pdf_base64}",
                    },
                },
                {"type": "text", "text": text_content},
            ]
        else:
            user_content = text_content

        request_payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "You are a precise research extraction engine. Return strict JSON only."},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
        }
        body = self._request_with_retry(request_payload)

        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = content
        return json.loads(text)

    def _request_with_retry(self, request_payload: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                request = urllib.request.Request(
                    url=f"{self.config.base_url.rstrip('/')}/chat/completions",
                    data=json.dumps(request_payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with self.urlopen(request, timeout=_DEFAULT_TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    time.sleep(delay)
        raise RuntimeError(f"LLM request failed after {_MAX_RETRIES} attempts: {last_error}") from last_error
