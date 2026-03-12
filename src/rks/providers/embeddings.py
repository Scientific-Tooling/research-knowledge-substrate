from __future__ import annotations

import hashlib
import math
import re


_SYNONYMS = {
    "accuracy": ["quality", "performance"],
    "quality": ["accuracy", "performance"],
    "benchmark": ["dataset", "evaluation"],
    "dataset": ["benchmark"],
    "model": ["architecture", "system"],
    "architecture": ["model", "system"],
    "method": ["approach", "technique"],
    "approach": ["method", "technique"],
}


class LocalHashEmbeddingProvider:
    model_name = "local-hash-v1"

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            index = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]

    def cosine_similarity(self, left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

    def _tokens(self, text: str) -> list[str]:
        base_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]+", text.lower())
        expanded = list(base_tokens)
        for token in base_tokens:
            expanded.extend(_SYNONYMS.get(token, []))
        return expanded
