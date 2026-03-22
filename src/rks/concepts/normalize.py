from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Matches a trailing parenthetical abbreviation, e.g. "Large Language Model (LLM)"
# Captures only short all-caps tokens (2–8 chars) to avoid matching full phrases.
_TRAILING_ABBREV_RE = re.compile(r'\s*\(([A-Z][A-Z0-9\-]{1,7})\)\s*$')


def extract_abbreviation(term: str) -> tuple[str, str | None]:
    """Split 'Full Name (ABBREV)' into ('Full Name', 'ABBREV').

    Returns the original term unchanged and None when no abbreviation is found.
    """
    m = _TRAILING_ABBREV_RE.search(term)
    if m:
        abbrev = m.group(1)
        base = term[: m.start()].strip()
        return base, abbrev
    return term, None


def canonicalize_term(term: str) -> str:
    # Unicode NFC normalisation prevents visually identical chars hashing differently.
    term = unicodedata.normalize("NFC", term)

    # Strip trailing parenthetical abbreviation before further processing.
    term, _ = extract_abbreviation(term)

    # Replace hyphens and underscores with spaces so "self-supervised" and
    # "self_supervised" both normalise to "Self Supervised".
    term = term.replace("-", " ").replace("_", " ")

    stripped = " ".join(term.split()).strip(" .,:;()[]{}")
    if not stripped:
        return stripped

    lowered = stripped.lower()
    for prefix in ("the ", "a ", "an ", "our ", "this ", "these ", "those "):
        if lowered.startswith(prefix):
            stripped = stripped[len(prefix):]
            lowered = stripped.lower()
            break

    if lowered.endswith("ies") and len(lowered) > 4:
        stripped = stripped[:-3] + "y"
    elif lowered.endswith("s") and len(lowered) > 4 and not lowered.endswith("ss"):
        stripped = stripped[:-1]

    parts = []
    for token in stripped.split():
        if token.isupper() or any(char.isdigit() for char in token):
            parts.append(token)
        elif len(token) <= 4 and token.upper() == token:
            parts.append(token)
        else:
            parts.append(token.capitalize())
    return " ".join(parts)


def alias_candidates(term: str) -> Iterable[str]:
    canonical = canonicalize_term(term)
    lowered = canonical.lower()
    yield canonical
    yield lowered
