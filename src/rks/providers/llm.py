from __future__ import annotations

import json
import urllib.request

from rks.config import LlmConfig
from rks.llm import validate_claims_result_payload, validate_summary_result_payload, validate_text_result_payload


class OpenAICompatibleLlmProvider:
    def __init__(self, config: LlmConfig, urlopen=urllib.request.urlopen):
        self.config = config
        self.urlopen = urlopen

    def extract_text(self, input_payload: dict) -> dict:
        prompt = {
            "task": "extract_research_text",
            "instructions": [
                "Return only JSON.",
                "Preserve readable research text.",
                "Return keys: text, paragraphs, warnings.",
            ],
            "input": input_payload,
        }
        response = validate_text_result_payload(self._chat_json(prompt))
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
                "Return keys: summary, evidence_claim_ids, open_questions.",
                "The summary should be concise and grounded in the input evidence.",
            ],
            "input": summary_input,
        }
        return validate_summary_result_payload(self._chat_json(prompt))

    def _chat_json(self, payload: dict) -> dict:
        request_payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "You are a precise research extraction engine. Return strict JSON only."},
                {"role": "user", "content": json.dumps(payload)},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            url=f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))

        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = content
        return json.loads(text)
