from __future__ import annotations

import io
import json
import unittest

from rks.config import LlmConfig
from rks.providers.llm import OpenAICompatibleLlmProvider


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LlmProviderTest(unittest.TestCase):
    def test_extract_text_and_parse_claims(self) -> None:
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "text": "Transformers improve translation accuracy.",
                                    "paragraphs": ["Transformers improve translation accuracy."],
                                    "warnings": [],
                                }
                            )
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "claims": [
                                        {
                                            "text": "Transformers improve translation accuracy.",
                                            "predicate": "improves",
                                            "object_text": "translation accuracy",
                                            "context": {"subject_text": "Transformers"},
                                            "evidence": {"paper_id": "p_000001"},
                                            "confidence": 0.9,
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            },
        ]

        def fake_urlopen(request):
            self.assertIn("/chat/completions", request.full_url)
            return _FakeResponse(responses.pop(0))

        provider = OpenAICompatibleLlmProvider(
            config=LlmConfig(base_url="https://example.test/v1", api_key="test-key", model="test-model"),
            urlopen=fake_urlopen,
        )

        text_payload = provider.extract_text({"rough_text": "raw text"})
        self.assertEqual(text_payload["extractor"], "llm_api")
        self.assertEqual(text_payload["paragraphs"][0], "Transformers improve translation accuracy.")

        claims = provider.parse_claims(text_payload)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["context"]["subject_text"], "Transformers")


if __name__ == "__main__":
    unittest.main()
