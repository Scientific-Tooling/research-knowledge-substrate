"""Deterministic lexical retrieval shared by all searchable repositories.

Rank live records so imports, merges and deletions cannot leave a stale index.
This scans the corpus once per query; no optional SQLite extension is required.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
LEXICAL_METHOD = "bm25-terms-v1"
PHRASE_METHOD = "literal-phrase-v1"
K1 = 1.2
B = 0.75


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", normalize_text(text))


def search_records(
    records: Iterable[T], query: str, fields: Callable[[T], Iterable[str | None]], *, mode: str = "lexical"
) -> list[T]:
    """Match literal phrases or rank the union of complete query-term matches.

    BM25 statistics cover all records of this object type, including nonmatches.
    Query terms occur once, in sorted order, for reproducible floating-point sums.
    Scores express retrieval relevance, not scientific support or confidence.
    """
    if mode not in {"lexical", "phrase"}:
        raise ValueError(f"Unsupported lexical search mode: {mode}")
    if not query.strip():
        return []
    documents = [(record, [value for value in fields(record) if value]) for record in records]
    if mode == "phrase":
        phrase = normalize_text(query.strip())
        return sorted(
            (record for record, values in documents if any(phrase in normalize_text(value) for value in values)),
            key=lambda record: record.id,
        )
    terms = sorted(set(tokenize(query)))
    if not terms or not documents:
        return []
    frequencies = [Counter(tokenize(" ".join(values))) for _, values in documents]
    lengths = [sum(frequency.values()) for frequency in frequencies]
    average = sum(lengths) / len(lengths)
    if not average:
        return []
    document_frequency = Counter(term for frequency in frequencies for term in terms if term in frequency)
    inverse = {
        term: math.log1p((len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
        for term in terms
    }
    scored = []
    for (record, _), frequency, length in zip(documents, frequencies, lengths):
        score = 0.0
        for term in terms:
            count = frequency[term]
            if count:
                score += inverse[term] * count * (K1 + 1) / (count + K1 * (1 - B + B * length / average))
        if score > 0:
            scored.append((record, score))
    return [record for record, _ in sorted(scored, key=lambda pair: (-pair[1], pair[0].id))]


def search_metadata(mode: str) -> dict:
    return {
        "method": PHRASE_METHOD if mode == "phrase" else LEXICAL_METHOD,
        "normalization": "Unicode NFKC and casefold",
        "ranking": "stable ID ascending" if mode == "phrase" else "BM25 descending, stable ID ascending on ties",
        "corpus_scope": "each object type independently; all live records; no cross-type cap",
        "parameters": {} if mode == "phrase" else {"k1": K1, "b": B},
        "query_policy": "literal substring within one field" if mode == "phrase" else (
            "unique Unicode alphanumeric terms; OR matching; no stemming, stop-word removal or query rewriting"
        ),
    }
