from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from rks import __version__
from rks.config import load_paths
from rks.extraction.pdf_backend import build_paragraph_records
from rks.extraction.text import detect_sections
from rks.operations import ResearchOperations
from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
from rks.reasoning.output import build_scoped_answer
from rks.storage import (
    CandidateRepository,
    ClaimRepository,
    ConceptRepository,
    ConflictClusterRepository,
    DatasetRepository,
    EmbeddingRepository,
    EdgeRepository,
    EvolutionRepository,
    HypothesisRepository,
    MethodRepository,
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    TaskRepository,
    connect_db,
    initialize_db,
)
from rks.utils import utc_now


logger = logging.getLogger("rks.mcp")

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "rks-mcp"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class _RepositoryContext:
    def __enter__(self):
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return {
            "papers": PaperRepository(self.conn),
            "projects": ProjectRepository(self.conn),
            "hypotheses": HypothesisRepository(self.conn),
            "claims": ClaimRepository(self.conn),
            "concepts": ConceptRepository(self.conn),
            "notes": NoteRepository(self.conn),
            "edges": EdgeRepository(self.conn),
            "methods": MethodRepository(self.conn),
            "datasets": DatasetRepository(self.conn),
            "embeddings": EmbeddingRepository(self.conn),
            "tasks": TaskRepository(self.conn),
            "candidates": CandidateRepository(self.conn),
            "evolution": EvolutionRepository(self.conn),
            "conflict_clusters": ConflictClusterRepository(self.conn),
        }

    def __exit__(self, exc_type, exc, tb):
        self.conn.close()


class _QueryContext:
    def __enter__(self):
        self._repo_context = _RepositoryContext()
        repos = self._repo_context.__enter__()
        return QueryService(
            papers=repos["papers"],
            claims=repos["claims"],
            concepts=repos["concepts"],
            edges=repos["edges"],
            methods=repos["methods"],
            datasets=repos["datasets"],
            embeddings=repos["embeddings"],
            embedding_provider=LocalHashEmbeddingProvider(),
        )

    def __exit__(self, exc_type, exc, tb):
        self._repo_context.__exit__(exc_type, exc, tb)


class _OperationsContext:
    def __enter__(self):
        self._repo_context = _RepositoryContext()
        repos = self._repo_context.__enter__()
        return ResearchOperations(
            papers=repos["papers"],
            projects=repos["projects"],
            hypotheses=repos["hypotheses"],
            claims=repos["claims"],
            concepts=repos["concepts"],
            notes=repos["notes"],
            edges=repos["edges"],
            methods=repos["methods"],
            datasets=repos["datasets"],
            embeddings=repos["embeddings"],
            tasks=repos["tasks"],
            candidates=repos["candidates"],
            evolution=repos["evolution"],
            conflict_clusters=repos["conflict_clusters"],
        )

    def __exit__(self, exc_type, exc, tb):
        self._repo_context.__exit__(exc_type, exc, tb)


def _open_repositories() -> _RepositoryContext:
    return _RepositoryContext()


def _open_query_service() -> _QueryContext:
    return _QueryContext()


def _open_operations() -> _OperationsContext:
    return _OperationsContext()


class RksMcpServer:
    def __init__(self) -> None:
        self._shutdown_requested = False
        self._chat_sessions: dict[str, dict] = {}

    def run_stdio(self) -> None:
        stdin = sys.stdin.buffer
        stdout = sys.stdout.buffer
        while not self._shutdown_requested:
            message = _read_framed_message(stdin)
            if message is None:
                break
            response = self.handle_message(message)
            if response is None:
                continue
            _write_framed_message(stdout, response)
            stdout.flush()

    def handle_message(self, message: dict) -> dict | None:
        if not isinstance(message, dict):
            return _jsonrpc_error_response(None, -32600, "Invalid Request")

        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return _jsonrpc_result_response(
                request_id,
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": _SERVER_NAME, "version": __version__},
                },
            )
        if method == "ping":
            return _jsonrpc_result_response(request_id, {})
        if method == "shutdown":
            self._shutdown_requested = True
            return _jsonrpc_result_response(request_id, {})
        if method == "exit":
            self._shutdown_requested = True
            return None
        if method == "tools/list":
            return _jsonrpc_result_response(request_id, {"tools": _tool_definitions()})
        if method == "tools/call":
            if not isinstance(params, dict):
                return _jsonrpc_error_response(request_id, -32602, "Invalid params")
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                return _jsonrpc_error_response(request_id, -32602, "Tool name must be a string")
            if not isinstance(arguments, dict):
                return _jsonrpc_error_response(request_id, -32602, "Tool arguments must be an object")
            result = self._call_tool(name, arguments)
            return _jsonrpc_result_response(request_id, result)
        return _jsonrpc_error_response(request_id, -32601, f"Method not found: {method}")

    def _call_tool(self, name: str, arguments: dict) -> dict:
        try:
            handlers = {
                "search_papers": self._tool_search_papers,
                "get_paper": self._tool_get_paper,
                "get_sections": self._tool_get_sections,
                "retrieve_passages": self._tool_retrieve_passages,
                "get_citation_spans": self._tool_get_citation_spans,
                "chat_with_paper": self._tool_chat_with_paper,
                "save_note": self._tool_save_note,
                "list_notes": self._tool_list_notes,
            }
            handler = handlers.get(name)
            if handler is None:
                return _tool_error(f"Unknown tool: {name}")
            payload = handler(arguments)
            return _tool_success(payload)
        except KeyError as exc:
            return _tool_error(str(exc))
        except ValueError as exc:
            return _tool_error(str(exc))
        except Exception:
            logger.exception("Unhandled MCP tool error for %s", name)
            return _tool_error("Internal server error while executing tool.")

    def _tool_search_papers(self, arguments: dict) -> dict:
        query = _as_text(arguments.get("query"), required=True, field="query")
        mode = _as_text(arguments.get("mode"), required=False, field="mode") or "hybrid"
        if mode not in {"lexical", "semantic", "hybrid"}:
            raise ValueError("mode must be one of: lexical, semantic, hybrid")

        filters = arguments.get("filters") or {}
        if not isinstance(filters, dict):
            raise ValueError("filters must be an object when provided")
        limit = _coerce_positive_int(filters.get("limit", 10), default=10, max_value=100)
        year_from = _coerce_optional_int(filters.get("year_from"))
        year_to = _coerce_optional_int(filters.get("year_to"))
        source_type = _as_text(filters.get("source_type"), required=False, field="filters.source_type")
        paper_ids_filter = _coerce_str_list(filters.get("paper_ids"))

        with _open_query_service() as query_service:
            search = query_service.search(query, mode=mode)

        papers = []
        for paper in search.get("papers", []):
            if paper_ids_filter and paper["id"] not in paper_ids_filter:
                continue
            if source_type and paper.get("source_type") != source_type:
                continue
            year = paper.get("year")
            if year_from is not None and (year is None or int(year) < year_from):
                continue
            if year_to is not None and (year is None or int(year) > year_to):
                continue
            papers.append(
                {
                    "id": paper["id"],
                    "title": paper["title"],
                    "abstract": paper.get("abstract"),
                    "year": paper.get("year"),
                    "venue": paper.get("venue"),
                    "doi": paper.get("doi"),
                    "arxiv_id": paper.get("arxiv_id"),
                    "source_type": paper.get("source_type"),
                    "source_ref": paper.get("source_ref"),
                    "semantic_score": paper.get("semantic_score"),
                }
            )
            if len(papers) >= limit:
                break

        return {
            "query": query,
            "mode": mode,
            "count": len(papers),
            "papers": papers,
        }

    def _tool_get_paper(self, arguments: dict) -> dict:
        paper_id = _as_text(arguments.get("paper_id"), required=True, field="paper_id")
        include_sections = bool(arguments.get("include_sections", True))
        include_notes = bool(arguments.get("include_notes", True))
        include_claims = bool(arguments.get("include_claims", False))

        with _open_repositories() as repos:
            paper = repos["papers"].get_paper(paper_id)
            artifacts = repos["papers"].get_artifacts_for_paper(paper_id)
            notes = repos["notes"].list_notes_for_target(target_id=paper_id, target_type="paper") if include_notes else []
            claims = repos["claims"].list_claims_for_paper(paper_id) if include_claims else []

            sections_payload = None
            if include_sections:
                sections_payload = _load_sections_payload(repos["papers"], paper_id)

        payload = {
            "paper": _paper_payload(paper),
            "artifacts": [
                {
                    "id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "path": artifact.path,
                    "format": artifact.format,
                    "metadata": _safe_json_loads(artifact.metadata_json, default={}),
                    "created_at": artifact.created_at,
                }
                for artifact in artifacts
            ],
        }
        if include_sections:
            payload["sections"] = (sections_payload or {}).get("sections", [])
        if include_notes:
            payload["notes"] = [_note_payload(note) for note in notes]
        if include_claims:
            payload["claims"] = [_claim_payload_for_mcp(claim) for claim in claims]
        return payload

    def _tool_get_sections(self, arguments: dict) -> dict:
        paper_id = _as_text(arguments.get("paper_id"), required=True, field="paper_id")
        with _open_repositories() as repos:
            repos["papers"].get_paper(paper_id)
            sections_payload = _load_sections_payload(repos["papers"], paper_id)
            if sections_payload is None:
                raise ValueError("No sections artifact available for this paper yet.")
        return {
            "paper_id": paper_id,
            "section_count": len(sections_payload.get("sections", [])),
            "sections": sections_payload.get("sections", []),
            "extractor": sections_payload.get("extractor"),
            "extractor_version": sections_payload.get("extractor_version"),
            "mode": sections_payload.get("mode"),
        }

    def _tool_retrieve_passages(self, arguments: dict) -> dict:
        paper_id = _as_text(arguments.get("paper_id"), required=True, field="paper_id")
        question = _as_text(arguments.get("question"), required=True, field="question")
        top_k = _coerce_positive_int(arguments.get("top_k", 5), default=5, max_value=20)

        with _open_repositories() as repos:
            repos["papers"].get_paper(paper_id)
            text_payload = _load_text_payload(repos["papers"], paper_id)
            if text_payload is None:
                raise ValueError("No extracted_text artifact available for this paper yet.")
            sections_payload = _load_sections_payload(repos["papers"], paper_id) or detect_sections(text_payload)
            claims = repos["claims"].list_claims_for_paper(paper_id)

        paragraph_records = text_payload.get("paragraph_records") or build_paragraph_records(text_payload.get("paragraphs", []))
        scored = []
        for record in paragraph_records:
            score = _passage_score(question, record.get("text", ""))
            section_name = _section_name_for_span(
                sections_payload.get("sections", []),
                int(record.get("char_start", 0)),
                int(record.get("char_end", 0)),
            )
            scored.append(
                {
                    "chunk_id": str(record["index"]),
                    "paper_id": paper_id,
                    "section": section_name,
                    "paragraph_index": int(record["index"]),
                    "char_start": int(record["char_start"]),
                    "char_end": int(record["char_end"]),
                    "text": record["text"],
                    "score": score,
                    "claim_ids": _claim_ids_for_paragraph(claims, int(record["index"]), int(record["char_start"]), int(record["char_end"])),
                }
            )

        ranked = sorted(scored, key=lambda item: (item["score"], -item["char_start"]), reverse=True)
        if ranked and ranked[0]["score"] <= 0:
            ranked = sorted(scored, key=lambda item: (len(item["text"]), -item["char_start"]), reverse=True)
        top = ranked[:top_k]

        return {
            "paper_id": paper_id,
            "question": question,
            "top_k": top_k,
            "passages": top,
        }

    def _tool_get_citation_spans(self, arguments: dict) -> dict:
        paper_id = _as_text(arguments.get("paper_id"), required=True, field="paper_id")
        chunk_ids = _coerce_str_list(arguments.get("chunk_ids"))
        if not chunk_ids:
            raise ValueError("chunk_ids must include at least one chunk id")

        with _open_repositories() as repos:
            repos["papers"].get_paper(paper_id)
            text_payload = _load_text_payload(repos["papers"], paper_id)
            if text_payload is None:
                raise ValueError("No extracted_text artifact available for this paper yet.")
            sections_payload = _load_sections_payload(repos["papers"], paper_id) or detect_sections(text_payload)
            claims = repos["claims"].list_claims_for_paper(paper_id)

        paragraph_records = text_payload.get("paragraph_records") or build_paragraph_records(text_payload.get("paragraphs", []))
        record_map = {str(record["index"]): record for record in paragraph_records}

        spans = []
        for chunk_id in chunk_ids:
            record = record_map.get(str(chunk_id))
            if record is None:
                continue
            char_start = int(record["char_start"])
            char_end = int(record["char_end"])
            section_name = _section_name_for_span(sections_payload.get("sections", []), char_start, char_end)
            citations = []
            for claim in claims:
                evidence = _safe_json_loads(claim.evidence_json, default={})
                if evidence.get("paragraph_index") == int(record["index"]) or _span_overlap(
                    char_start,
                    char_end,
                    int(evidence.get("char_start") or -1),
                    int(evidence.get("char_end") or -1),
                ):
                    citations.append(
                        {
                            "claim_id": claim.id,
                            "snippet": evidence.get("snippet"),
                            "char_start": evidence.get("char_start"),
                            "char_end": evidence.get("char_end"),
                            "section": evidence.get("section"),
                        }
                    )
            spans.append(
                {
                    "chunk_id": str(record["index"]),
                    "paper_id": paper_id,
                    "section": section_name,
                    "paragraph_index": int(record["index"]),
                    "char_start": char_start,
                    "char_end": char_end,
                    "text": record["text"],
                    "citations": citations,
                }
            )

        return {
            "paper_id": paper_id,
            "requested_chunk_ids": chunk_ids,
            "spans": spans,
        }

    def _tool_chat_with_paper(self, arguments: dict) -> dict:
        session_id = _as_text(arguments.get("session_id"), required=False, field="session_id")
        if not session_id:
            session_id = f"session_{utc_now().replace(':', '').replace('-', '').replace('T', '_')}"
        message = _as_text(arguments.get("message"), required=True, field="message")
        paper_ids = _coerce_str_list(arguments.get("paper_ids"))
        options = arguments.get("options") or {}
        if not isinstance(options, dict):
            raise ValueError("options must be an object when provided")

        session = self._chat_sessions.setdefault(
            session_id,
            {"session_id": session_id, "paper_ids": [], "messages": [], "created_at": utc_now(), "updated_at": utc_now()},
        )
        if paper_ids:
            session["paper_ids"] = _dedupe_ids(session["paper_ids"] + paper_ids)
        active_paper_ids = session["paper_ids"]
        if not active_paper_ids:
            raise ValueError("paper_ids are required for a new session")

        session["messages"].append({"role": "user", "content": message, "created_at": utc_now()})
        max_history = _coerce_positive_int(options.get("history_turns", 3), default=3, max_value=10)
        history = [entry["content"] for entry in session["messages"] if entry["role"] == "user"][-max_history:]
        question = message
        if len(history) > 1:
            question = "Context from previous turns:\n" + "\n".join(history[:-1]) + "\n\nCurrent question:\n" + message

        with _open_query_service() as query_service:
            context = _paper_scope_context(query_service, active_paper_ids)
            answer_payload = build_scoped_answer(
                query_service,
                "paper_set",
                ", ".join(active_paper_ids),
                context,
                question=question,
            )

        citations = _citations_from_supporting_claims(answer_payload.get("supporting_claims", []), active_paper_ids)
        if not citations and active_paper_ids:
            fallback = self._tool_retrieve_passages(
                {"paper_id": active_paper_ids[0], "question": message, "top_k": options.get("fallback_passages", 3)}
            )
            citations = [
                {
                    "paper_id": active_paper_ids[0],
                    "chunk_id": passage["chunk_id"],
                    "section": passage["section"],
                    "paragraph_index": passage["paragraph_index"],
                    "char_start": passage["char_start"],
                    "char_end": passage["char_end"],
                    "snippet": passage["text"],
                }
                for passage in fallback.get("passages", [])
            ]

        answer_text = answer_payload.get("answer", "")
        session["messages"].append({"role": "assistant", "content": answer_text, "created_at": utc_now()})
        session["updated_at"] = utc_now()

        return {
            "session_id": session_id,
            "paper_ids": active_paper_ids,
            "turn_count": len(session["messages"]),
            "answer": answer_text,
            "conclusion": answer_payload.get("conclusion"),
            "confidence": answer_payload.get("confidence"),
            "supporting_claims": answer_payload.get("supporting_claims", []),
            "supporting_papers": answer_payload.get("supporting_papers", []),
            "next_steps": answer_payload.get("next_steps", []),
            "citations": citations,
        }

    def _tool_save_note(self, arguments: dict) -> dict:
        session_id = _as_text(arguments.get("session_id"), required=True, field="session_id")
        paper_id = _as_text(arguments.get("paper_id"), required=True, field="paper_id")
        note = _as_text(arguments.get("note"), required=True, field="note")
        created_by = _as_text(arguments.get("created_by"), required=False, field="created_by") or f"agent:mcp:{session_id}"

        with _open_operations() as operations:
            payload = operations.add_paper_note(
                paper_id,
                content=note,
                created_by=created_by,
            )
        session = self._chat_sessions.setdefault(
            session_id,
            {"session_id": session_id, "paper_ids": [paper_id], "messages": [], "created_at": utc_now(), "updated_at": utc_now()},
        )
        session["paper_ids"] = _dedupe_ids(session["paper_ids"] + [paper_id])
        session["updated_at"] = utc_now()
        return {"session_id": session_id, "note": payload}

    def _tool_list_notes(self, arguments: dict) -> dict:
        paper_id = _as_text(arguments.get("paper_id"), required=False, field="paper_id")
        session_id = _as_text(arguments.get("session_id"), required=False, field="session_id")

        if not paper_id and not session_id:
            raise ValueError("Either paper_id or session_id is required")

        with _open_operations() as operations:
            if paper_id:
                notes = operations.list_paper_notes(paper_id)
                return {"paper_id": paper_id, "notes": notes}

            session = self._chat_sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id}")
            paper_notes = []
            for pid in session.get("paper_ids", []):
                paper_notes.append({"paper_id": pid, "notes": operations.list_paper_notes(pid)})
            return {"session_id": session_id, "papers": paper_notes}


def _tool_definitions() -> list[dict]:
    return [
        {
            "name": "search_papers",
            "description": "Search papers in the local RKS graph by query text.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {"type": "string", "enum": ["lexical", "semantic", "hybrid"]},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer"},
                            "year_from": {"type": "integer"},
                            "year_to": {"type": "integer"},
                            "source_type": {"type": "string"},
                            "paper_ids": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_paper",
            "description": "Get paper metadata, artifacts, and optional sections/notes/claims.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string"},
                    "include_sections": {"type": "boolean"},
                    "include_notes": {"type": "boolean"},
                    "include_claims": {"type": "boolean"},
                },
                "required": ["paper_id"],
            },
        },
        {
            "name": "get_sections",
            "description": "Return parsed sections for a paper with paragraph and character offsets.",
            "inputSchema": {
                "type": "object",
                "properties": {"paper_id": {"type": "string"}},
                "required": ["paper_id"],
            },
        },
        {
            "name": "retrieve_passages",
            "description": "Retrieve the most relevant paragraphs for a question in one paper.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string"},
                    "question": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                "required": ["paper_id", "question"],
            },
        },
        {
            "name": "get_citation_spans",
            "description": "Get citation-ready spans for paragraph chunk ids in a paper.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string"},
                    "chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paper_id", "chunk_ids"],
            },
        },
        {
            "name": "chat_with_paper",
            "description": "Run a grounded QA turn over one or more papers with session memory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "message": {"type": "string"},
                    "paper_ids": {"type": "array", "items": {"type": "string"}},
                    "options": {"type": "object"},
                },
                "required": ["message"],
            },
        },
        {
            "name": "save_note",
            "description": "Save a paper note associated with a chat session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "paper_id": {"type": "string"},
                    "note": {"type": "string"},
                    "created_by": {"type": "string"},
                },
                "required": ["session_id", "paper_id", "note"],
            },
        },
        {
            "name": "list_notes",
            "description": "List notes for one paper or all papers in a session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string"},
                    "session_id": {"type": "string"},
                },
            },
        },
    ]


def _read_framed_message(stream) -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if line == b"":
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.lower().strip()] = value.strip()

    content_length = headers.get("content-length")
    if content_length is None:
        return None
    size = int(content_length)
    body = stream.read(size)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_framed_message(stream, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(body)


def _jsonrpc_result_response(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error_response(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_success(payload: dict) -> dict:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "structuredContent": payload, "isError": False}


def _tool_error(message: str) -> dict:
    payload = {"error": message}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload,
        "isError": True,
    }


def _as_text(value, *, required: bool, field: str) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if required and not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _coerce_positive_int(value, *, default: int, max_value: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("Value must be a positive integer")
    return min(parsed, max_value)


def _coerce_optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_str_list(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected an array of strings")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Expected an array of strings")
        normalized = item.strip()
        if normalized:
            result.append(normalized)
    return result


def _dedupe_ids(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _safe_json_loads(value: str | None, *, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _paper_payload(paper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": _safe_json_loads(paper.authors_json, default=[]),
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "source_type": paper.source_type,
        "source_ref": paper.source_ref,
        "pdf_path": paper.pdf_path,
        "text_artifact_id": paper.text_artifact_id,
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
    }


def _note_payload(note) -> dict:
    return {
        "id": note.id,
        "target_id": note.target_id,
        "target_type": note.target_type,
        "content": note.content,
        "created_by": note.created_by,
        "created_at": note.created_at,
    }


def _claim_payload_for_mcp(claim) -> dict:
    return {
        "id": claim.id,
        "paper_id": claim.paper_id,
        "text": claim.text,
        "predicate": claim.predicate,
        "object_text": claim.object_text,
        "context": _safe_json_loads(claim.context_json, default={}),
        "evidence": _safe_json_loads(claim.evidence_json, default={}),
        "confidence": claim.confidence,
        "status": claim.status,
        "created_by": claim.created_by,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
    }


def _find_artifact_by_type(paper_repo: PaperRepository, paper_id: str, artifact_type: str):
    artifacts = paper_repo.get_artifacts_for_paper(paper_id)
    for artifact in reversed(artifacts):
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def _load_text_payload(paper_repo: PaperRepository, paper_id: str) -> dict | None:
    artifact = _find_artifact_by_type(paper_repo, paper_id, "extracted_text")
    if artifact is None:
        return None
    artifact_path = Path(artifact.path)
    if not artifact_path.exists():
        return None
    return json.loads(artifact_path.read_text(encoding="utf-8"))


def _load_sections_payload(paper_repo: PaperRepository, paper_id: str) -> dict | None:
    artifact = _find_artifact_by_type(paper_repo, paper_id, "sections")
    if artifact is not None:
        sections_path = Path(artifact.path)
        if sections_path.exists():
            return json.loads(sections_path.read_text(encoding="utf-8"))
    text_payload = _load_text_payload(paper_repo, paper_id)
    if text_payload is None:
        return None
    return detect_sections(text_payload)


def _section_name_for_span(sections: list[dict], char_start: int, char_end: int) -> str | None:
    for section in sections:
        start = int(section.get("char_start", -1))
        end = int(section.get("char_end", -1))
        if _span_overlap(char_start, char_end, start, end):
            return section.get("name")
    return None


def _claim_ids_for_paragraph(claims: list, paragraph_index: int, char_start: int, char_end: int) -> list[str]:
    claim_ids = []
    for claim in claims:
        evidence = _safe_json_loads(claim.evidence_json, default={})
        evidence_paragraph = evidence.get("paragraph_index")
        if evidence_paragraph is not None and int(evidence_paragraph) == paragraph_index:
            claim_ids.append(claim.id)
            continue
        evidence_start = evidence.get("char_start")
        evidence_end = evidence.get("char_end")
        if evidence_start is None or evidence_end is None:
            continue
        if _span_overlap(char_start, char_end, int(evidence_start), int(evidence_end)):
            claim_ids.append(claim.id)
    return claim_ids


def _span_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    if left_start < 0 or left_end < 0 or right_start < 0 or right_end < 0:
        return False
    return max(left_start, right_start) <= min(left_end, right_end)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _passage_score(question: str, passage_text: str) -> float:
    if not question.strip() or not passage_text.strip():
        return 0.0
    question_tokens = _tokenize(question)
    passage_tokens = _tokenize(passage_text)
    if not question_tokens or not passage_tokens:
        return 0.0
    question_set = set(question_tokens)
    passage_set = set(passage_tokens)
    overlap = len(question_set & passage_set)
    coverage = overlap / len(question_set)
    phrase_bonus = 0.0
    normalized_question = " ".join(question.lower().split())
    if len(normalized_question) > 8 and normalized_question in " ".join(passage_text.lower().split()):
        phrase_bonus = 1.5
    return float(overlap) + coverage + phrase_bonus


def _paper_scope_context(query_service: QueryService, paper_ids: list[str]) -> dict:
    papers = []
    claims = []
    methods = []
    datasets = []
    claim_ids: list[str] = []

    for paper_id in _dedupe_ids(paper_ids):
        paper = query_service.papers.get_paper(paper_id)
        papers.append(query_service._paper_payload(paper))

        for claim in query_service.claims.list_claims_for_paper(paper_id):
            payload = query_service._claim_payload(claim)
            claims.append(payload)

        if query_service.methods is not None:
            methods.extend(
                {
                    "id": method.id,
                    "paper_id": method.paper_id,
                    "name": method.name,
                    "description": method.description,
                }
                for method in query_service.methods.list_methods_for_paper(paper_id)
            )
        if query_service.datasets is not None:
            datasets.extend(
                {
                    "id": dataset.id,
                    "paper_id": dataset.paper_id,
                    "name": dataset.name,
                    "description": dataset.description,
                }
                for dataset in query_service.datasets.list_datasets_for_paper(paper_id)
            )

    claims = _dedupe_objects(claims)
    methods = _dedupe_objects(methods)
    datasets = _dedupe_objects(datasets)
    papers = _dedupe_objects(papers)

    claims = sorted(claims, key=lambda item: (item.get("confidence") or 0.0, item["id"]), reverse=True)
    methods = sorted(methods, key=lambda item: (item["name"].lower(), item["id"]))
    datasets = sorted(datasets, key=lambda item: (item["name"].lower(), item["id"]))
    papers = sorted(papers, key=lambda item: (item["title"].lower(), item["id"]))
    claim_ids = [claim["id"] for claim in claims[:12]]

    return {
        "claims": claims,
        "claim_ids": claim_ids,
        "papers": papers,
        "methods": methods,
        "datasets": datasets,
    }


def _dedupe_objects(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _citations_from_supporting_claims(claims: list[dict], scoped_paper_ids: list[str]) -> list[dict]:
    citations = []
    seen = set()
    scope = set(scoped_paper_ids)
    for claim in claims:
        evidence = claim.get("evidence") or {}
        paper_id = claim.get("paper_id") or evidence.get("paper_id")
        if not paper_id or paper_id not in scope:
            continue
        key = (
            paper_id,
            evidence.get("paragraph_index"),
            evidence.get("char_start"),
            evidence.get("char_end"),
            claim.get("id"),
        )
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "paper_id": paper_id,
                "claim_id": claim.get("id"),
                "section": evidence.get("section"),
                "paragraph_index": evidence.get("paragraph_index"),
                "char_start": evidence.get("char_start"),
                "char_end": evidence.get("char_end"),
                "snippet": evidence.get("snippet"),
            }
        )
    return citations


def serve_mcp_stdio() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stderr,
    )
    server = RksMcpServer()
    server.run_stdio()
