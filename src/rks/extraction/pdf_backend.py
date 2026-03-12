from __future__ import annotations

import re
import string
import zlib
from pathlib import Path


PDF_EXTRACTOR_NAME = "pdf_stream_decoder"
PDF_EXTRACTOR_VERSION = "1.0"
KNOWN_SECTION_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "method",
    "methods",
    "approach",
    "experiment",
    "experiments",
    "evaluation",
    "results",
    "discussion",
    "conclusion",
}

_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_HEX_PATTERN = re.compile(r"<([0-9A-Fa-f\s]+)>")
_LITERAL_PATTERN = re.compile(r"\((?:\\.|[^\\)])+\)")


def extract_pdf_text(pdf_path: Path | None) -> dict:
    warnings: list[str] = []
    if pdf_path is None or not pdf_path.exists():
        return {
            "extractor": "unavailable",
            "extractor_version": PDF_EXTRACTOR_VERSION,
            "text": "",
            "paragraphs": [],
            "paragraph_records": [],
            "warnings": ["PDF path is missing; no text could be extracted."],
        }

    raw_bytes = pdf_path.read_bytes()
    fragments = _extract_pdf_fragments(raw_bytes)
    if not fragments:
        fragments = _fallback_ascii_fragments(raw_bytes)
        warnings.append("Fell back to plain-text byte scanning because structured PDF extraction was sparse.")

    paragraph_records = build_paragraph_records(fragments)
    return {
        "extractor": PDF_EXTRACTOR_NAME,
        "extractor_version": PDF_EXTRACTOR_VERSION,
        "text": "\n\n".join(record["text"] for record in paragraph_records),
        "paragraphs": [record["text"] for record in paragraph_records],
        "paragraph_records": paragraph_records,
        "warnings": warnings,
    }


def build_paragraph_records(paragraphs: list[str]) -> list[dict]:
    records: list[dict] = []
    offset = 0
    for index, paragraph in enumerate(_normalize_paragraphs(paragraphs)):
        start = offset
        end = start + len(paragraph)
        records.append(
            {
                "index": index,
                "text": paragraph,
                "char_start": start,
                "char_end": end,
            }
        )
        offset = end + 2
    return records


def _extract_pdf_fragments(raw_bytes: bytes) -> list[str]:
    fragments: list[str] = []
    for match in _STREAM_PATTERN.finditer(raw_bytes):
        stream_bytes = _decode_stream(raw_bytes, match)
        if not stream_bytes:
            continue
        decoded = stream_bytes.decode("latin-1", errors="ignore")
        fragments.extend(_extract_text_tokens(decoded))
    return _normalize_paragraphs(fragments)


def _decode_stream(raw_bytes: bytes, match: re.Match[bytes]) -> bytes:
    stream = match.group(1).strip(b"\r\n")
    header = raw_bytes[max(0, match.start() - 256) : match.start()]
    if b"FlateDecode" in header:
        try:
            return zlib.decompress(stream)
        except zlib.error:
            return b""
    return stream


def _extract_text_tokens(decoded: str) -> list[str]:
    tokens: list[str] = []
    tokens.extend(_decode_literal_strings(decoded))
    tokens.extend(_decode_hex_strings(decoded))

    if tokens:
        return tokens

    printable_runs = re.findall(r"[A-Za-z0-9][A-Za-z0-9 ,:;()/%+\-]{12,}", decoded)
    return [value.strip() for value in printable_runs]


def _decode_literal_strings(decoded: str) -> list[str]:
    values: list[str] = []
    for match in _LITERAL_PATTERN.finditer(decoded):
        token = match.group(0)[1:-1]
        token = re.sub(r"\\([\\()])", r"\1", token)
        token = token.replace(r"\n", "\n").replace(r"\r", " ").replace(r"\t", " ")
        cleaned = _clean_fragment(token)
        if cleaned:
            values.append(cleaned)
    return values


def _decode_hex_strings(decoded: str) -> list[str]:
    values: list[str] = []
    for match in _HEX_PATTERN.finditer(decoded):
        hex_value = "".join(match.group(1).split())
        if len(hex_value) < 8 or len(hex_value) % 2 != 0:
            continue
        try:
            token = bytes.fromhex(hex_value).decode("utf-8")
        except UnicodeDecodeError:
            try:
                token = bytes.fromhex(hex_value).decode("latin-1")
            except UnicodeDecodeError:
                continue
        cleaned = _clean_fragment(token)
        if cleaned:
            values.append(cleaned)
    return values


def _fallback_ascii_fragments(raw_bytes: bytes) -> list[str]:
    text = raw_bytes.decode("latin-1", errors="ignore")
    fragments = []
    for line in text.splitlines():
        stripped = line.strip()
        if _looks_like_pdf_scaffolding(stripped):
            continue
        if len(stripped) < 12 and stripped.lower().rstrip(":") not in KNOWN_SECTION_HEADINGS:
            continue
        if not _has_letter(stripped):
            continue
        fragments.append(_clean_fragment(stripped))
    return _normalize_paragraphs(fragments)


def _normalize_paragraphs(paragraphs: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        cleaned = _clean_fragment(paragraph)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _clean_fragment(value: str) -> str:
    collapsed = " ".join(value.replace("\x00", " ").split())
    collapsed = collapsed.strip(" ")
    if len(collapsed) < 4:
        return ""
    if not _has_letter(collapsed):
        return ""
    if all(char in string.punctuation for char in collapsed):
        return ""
    return collapsed


def _has_letter(value: str) -> bool:
    return any(char.isalpha() for char in value)


def _looks_like_pdf_scaffolding(line: str) -> bool:
    lowered = line.lower()
    return lowered.startswith("%pdf-") or lowered in {
        "endobj",
        "stream",
        "endstream",
        "xref",
        "trailer",
        "%%eof",
    }
