from __future__ import annotations

from typing import Iterable


def canonicalize_term(term: str) -> str:
    stripped = " ".join(term.replace("_", " ").split()).strip(" .,:;()[]{}")
    if not stripped:
        return stripped

    lowered = stripped.lower()
    for prefix in ("the ", "a ", "an ", "our ", "this ", "these ", "those "):
        if lowered.startswith(prefix):
            stripped = stripped[len(prefix) :]
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
