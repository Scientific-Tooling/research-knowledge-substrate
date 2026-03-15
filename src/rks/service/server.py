from __future__ import annotations

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("rks.service")

from rks.config import load_paths
from rks.operations import ResearchOperations
from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
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


def serve_http(host: str, port: int) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stderr,
    )
    logger.info("Starting RKS HTTP service on %s:%d (local-only)", host, port)
    server = ThreadingHTTPServer((host, port), _build_handler())
    server.serve_forever()


def _build_handler():
    class RksHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            logger.info("GET %s", self.path)
            try:
                status_code, content_type, body = dispatch_get_request(self.path)
            except KeyError:
                logger.warning("GET %s -> 404", self.path)
                self.send_error(404, "Not found")
                return
            except Exception:
                logger.exception("GET %s -> 500", self.path)
                self.send_error(500, "Internal server error")
                return
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            logger.info("POST %s", self.path)
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length else b"{}"
                status_code, content_type, body = dispatch_post_request(self.path, raw_body)
            except KeyError:
                logger.warning("POST %s -> 404", self.path)
                self.send_error(404, "Not found")
                return
            except ValueError as exc:
                logger.warning("POST %s -> 400: %s", self.path, exc)
                self.send_error(400, str(exc))
                return
            except Exception:
                logger.exception("POST %s -> 500", self.path)
                self.send_error(500, "Internal server error")
                return
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return None

    return RksHandler


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


def _open_repositories() -> _RepositoryContext:
    return _RepositoryContext()


def _open_query_service() -> _QueryContext:
    return _QueryContext()


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


def _open_operations() -> _OperationsContext:
    return _OperationsContext()


def _ui_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>RKS Workspace</title>
    <style>
      :root { color-scheme: light; --bg:#f2efe8; --panel:#fffdf8; --ink:#1f2a30; --accent:#a33b1f; }
      body { margin:0; font-family: Georgia, "Times New Roman", serif; background:linear-gradient(180deg,#ece4d6,#f8f5ef); color:var(--ink); }
      main { max-width:960px; margin:0 auto; padding:32px 20px 48px; }
      h1 { margin:0 0 8px; font-size:42px; letter-spacing:.02em; }
      .hero { background:var(--panel); border:1px solid #d8c9b7; border-radius:20px; padding:24px; box-shadow:0 12px 32px rgba(31,42,48,.08); }
      input, button { font:inherit; }
      input { width:70%; padding:12px 14px; border-radius:999px; border:1px solid #c7b39e; background:#fff; }
      button { padding:12px 18px; border:none; border-radius:999px; background:var(--accent); color:#fff; cursor:pointer; }
      pre { white-space:pre-wrap; background:#1f2a30; color:#f8f5ef; padding:16px; border-radius:16px; margin-top:20px; }
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1>RKS Workspace</h1>
        <p>Search the local research graph with lexical and semantic retrieval.</p>
        <form id="search-form">
          <input id="query" value="Transformer quality benchmark" aria-label="Search query">
          <button type="submit">Search</button>
        </form>
        <pre id="output">Run a search to inspect the current graph.</pre>
      </section>
    </main>
    <script>
      const form = document.getElementById('search-form');
      const output = document.getElementById('output');
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const query = document.getElementById('query').value;
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&mode=hybrid`);
        const payload = await response.json();
        output.textContent = JSON.stringify(payload, null, 2);
      });
    </script>
  </body>
</html>"""


def dispatch_get_request(path: str) -> tuple[int, str, bytes]:
    parsed = urlparse(path)
    if parsed.path == "/":
        return 200, "text/html; charset=utf-8", _ui_html().encode("utf-8")
    if parsed.path == "/health":
        return 200, "application/json", json.dumps({"status": "ok"}).encode("utf-8")
    if parsed.path == "/api/projects":
        with _open_operations() as operations:
            payload = operations.list_projects()
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/hypotheses/") and parsed.path.endswith("/evidence"):
        hypothesis_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            payload = operations.list_hypothesis_evidence(hypothesis_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/hypotheses/"):
        hypothesis_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.get_hypothesis(hypothesis_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/search":
        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0]
        mode = params.get("mode", ["hybrid"])[0]
        with _open_query_service() as query_service:
            payload = query_service.search(query, mode=mode)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/answer":
        params = parse_qs(parsed.query)
        question = params.get("q", [""])[0]
        with _open_operations() as operations:
            payload = operations.answer_question(question)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/brief":
        params = parse_qs(parsed.query)
        topic = params.get("topic", [""])[0]
        with _open_operations() as operations:
            payload = operations.topic_brief(topic)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/disagreements":
        params = parse_qs(parsed.query)
        topic = params.get("topic", [""])[0]
        with _open_operations() as operations:
            payload = operations.topic_disagreements(topic)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/opportunities":
        params = parse_qs(parsed.query)
        topic = params.get("topic", [""])[0]
        with _open_operations() as operations:
            payload = operations.research_opportunities(topic)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/reading-list":
        params = parse_qs(parsed.query)
        topic = params.get("topic", [""])[0]
        with _open_operations() as operations:
            payload = operations.topic_reading_list(topic)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/compare":
        params = parse_qs(parsed.query)
        left = params.get("left", [""])[0]
        right = params.get("right", [""])[0]
        with _open_operations() as operations:
            payload = operations.compare_targets(left, right)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/open-questions":
        params = parse_qs(parsed.query)
        topic = params.get("topic", [""])[0]
        with _open_operations() as operations:
            payload = operations.topic_open_questions(topic)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/output/review-priorities":
        params = parse_qs(parsed.query)
        topic = params.get("topic", [""])[0]
        with _open_operations() as operations:
            payload = operations.topic_review_priorities(topic)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/plan/query":
        params = parse_qs(parsed.query)
        request = params.get("q", [""])[0]
        project_id = params.get("project_id", [None])[0]
        with _open_operations() as operations:
            payload = operations.plan_query(request, project_id=project_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/output/projects/"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 5:
            raise KeyError(path)
        project_id = parts[3]
        surface = parts[4]
        params = parse_qs(parsed.query)
        with _open_operations() as operations:
            if surface == "answer":
                payload = operations.project_answer(project_id, question=params.get("q", [""])[0] or None)
            elif surface == "brief":
                payload = operations.project_brief(project_id)
            elif surface == "disagreements":
                payload = operations.project_disagreements(project_id)
            elif surface == "opportunities":
                payload = operations.project_opportunities(project_id)
            elif surface == "reading-list":
                payload = operations.project_reading_list(project_id)
            elif surface == "open-questions":
                payload = operations.project_open_questions(project_id)
            elif surface == "review-priorities":
                payload = operations.project_review_priorities(project_id)
            else:
                raise KeyError(path)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/claims/") and parsed.path.endswith("/relations"):
        claim_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            payload = operations.claim_relations(claim_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/review/candidates":
        params = parse_qs(parsed.query)
        claim_id = params.get("claim_id", [None])[0]
        status = params.get("status", [None])[0]
        with _open_operations() as operations:
            payload = operations.list_relation_candidates(claim_id=claim_id, status=status)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/evolution/events/"):
        subject_id = parsed.path.rsplit("/", 1)[-1]
        params = parse_qs(parsed.query)
        subject_type = params.get("type", [None])[0]
        with _open_operations() as operations:
            payload = operations.list_evolution_events(subject_id, subject_type=subject_type)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/evolution/concept-timeline/"):
        concept_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.concept_timeline(concept_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/evolution/hypothesis/"):
        hypothesis_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.build_hypothesis_evolution(hypothesis_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/evolution/conflict-clusters/"):
        concept_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.list_conflict_clusters(concept_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/evolution/concept-consensus/"):
        concept_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.concept_timeline(concept_id)
            snapshots = payload.get("snapshots", [])
            latest = snapshots[-1] if snapshots else {}
            payload = {
                "concept": payload.get("concept", {}),
                "consensus_score": latest.get("consensus_score"),
                "controversy_score": latest.get("controversy_score"),
                "snapshot_count": len(snapshots),
            }
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/query/review-priorities":
        params = parse_qs(parsed.query)
        scope_type = params.get("scope_type", ["concept"])[0]
        scope_id = params.get("scope_id", [None])[0]
        with _open_operations() as operations:
            payload = operations.compute_review_priorities(scope_type=scope_type, scope_id=scope_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/query/open-questions":
        params = parse_qs(parsed.query)
        scope_type = params.get("scope_type", ["concept"])[0]
        scope_id = params.get("scope_id", [None])[0]
        with _open_operations() as operations:
            payload = operations.compute_open_questions(scope_type=scope_type, scope_id=scope_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/evolution/project/"):
        project_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.project_evolution_summary(project_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/notes"):
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            payload = operations.list_project_notes(project_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/hypotheses"):
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            payload = operations.list_project_hypotheses(project_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/links"):
        project_id = parsed.path.split("/")[3]
        params = parse_qs(parsed.query)
        object_type = params.get("object_type", [None])[0]
        with _open_operations() as operations:
            payload = operations.list_project_links(project_id, object_type=object_type)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/papers"):
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            payload = operations.list_project_papers(project_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/projects/"):
        project_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.get_project(project_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/papers/") and parsed.path.endswith("/notes"):
        paper_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            payload = operations.list_paper_notes(paper_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/papers/"):
        paper_id = parsed.path.rsplit("/", 1)[-1]
        with _open_repositories() as repos:
            paper = repos["papers"].get_paper(paper_id)
            artifacts = repos["papers"].get_artifacts_for_paper(paper_id)
            notes = repos["notes"].list_notes_for_target(target_id=paper_id, target_type="paper")
            payload = {
                "id": paper.id,
                "title": paper.title,
                "source_type": paper.source_type,
                "source_ref": paper.source_ref,
                "pdf_path": paper.pdf_path,
                "artifacts": [artifact.artifact_type for artifact in artifacts],
                "notes": [
                    {
                        "id": note.id,
                        "target_id": note.target_id,
                        "target_type": note.target_type,
                        "content": note.content,
                        "created_by": note.created_by,
                        "created_at": note.created_at,
                    }
                    for note in notes
                ],
                "source_pdf": _source_pdf_status(paper, artifacts),
            }
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/extraction-quality":
        with _open_operations() as operations:
            payload = operations.extraction_quality_report()
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/status/"):
        paper_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            payload = operations.paper_status(paper_id)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path == "/api/tasks":
        with _open_repositories() as repos:
            tasks = repos["tasks"].list_tasks()
            payload = [
                {"id": task.id, "paper_id": task.paper_id, "task_type": task.task_type, "status": task.status}
                for task in tasks
            ]
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    raise KeyError(path)


def _require_fields(payload: dict, *fields: str) -> None:
    missing = [f for f in fields if f not in payload]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def dispatch_post_request(path: str, body: bytes) -> tuple[int, str, bytes]:
    parsed = urlparse(path)
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    if parsed.path == "/api/projects":
        _require_fields(payload, "name")
        with _open_operations() as operations:
            response = operations.create_project(
                name=payload["name"],
                description=payload.get("description"),
                research_question=payload.get("research_question"),
                status=payload.get("status", "active"),
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/hypotheses/") and parsed.path.endswith("/evidence"):
        _require_fields(payload, "object_type", "object_id")
        hypothesis_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            response = operations.add_hypothesis_evidence(
                hypothesis_id,
                payload["object_type"],
                payload["object_id"],
                relation_type=payload.get("relation_type", "supported_by"),
                note=payload.get("note"),
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path == "/api/review/claim-relations/promote":
        _require_fields(payload, "source_claim_id", "relation_type", "target_claim_id")
        with _open_operations() as operations:
            response = operations.promote_claim_relation(
                source_claim_id=payload["source_claim_id"],
                relation_type=payload["relation_type"],
                target_claim_id=payload["target_claim_id"],
                confidence=float(payload.get("confidence", 1.0)),
                reviewed_by=payload.get("reviewed_by", "agent:review"),
                note=payload.get("note"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path == "/api/review/claim-relations/retract":
        _require_fields(payload, "source_claim_id", "relation_type", "target_claim_id")
        with _open_operations() as operations:
            response = operations.retract_claim_relation(
                source_claim_id=payload["source_claim_id"],
                relation_type=payload["relation_type"],
                target_claim_id=payload["target_claim_id"],
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/notes"):
        _require_fields(payload, "content")
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            response = operations.add_project_note(
                project_id,
                content=payload["content"],
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/hypotheses"):
        _require_fields(payload, "text")
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            response = operations.create_hypothesis(
                project_id,
                text=payload["text"],
                status=payload.get("status", "draft"),
                confidence=payload.get("confidence"),
                context=payload.get("context"),
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/links"):
        _require_fields(payload, "object_type", "object_id")
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            response = operations.add_project_link(
                project_id,
                payload["object_type"],
                payload["object_id"],
                link_type=payload.get("link_type", "in_scope"),
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/papers"):
        _require_fields(payload, "paper_id")
        project_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            response = operations.add_project_paper(
                project_id,
                payload["paper_id"],
                link_type=payload.get("link_type", "in_scope"),
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/papers/") and parsed.path.endswith("/notes"):
        _require_fields(payload, "content")
        paper_id = parsed.path.split("/")[3]
        with _open_operations() as operations:
            response = operations.add_paper_note(
                paper_id,
                content=payload["content"],
                created_by=payload.get("created_by", "human:http"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path == "/api/review/materialize-candidates":
        with _open_operations() as operations:
            response = operations.materialize_claim_relation_candidates(
                claim_id=payload.get("claim_id"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path == "/api/review/promote-candidate":
        _require_fields(payload, "candidate_id")
        with _open_operations() as operations:
            response = operations.promote_candidate(
                candidate_id=payload["candidate_id"],
                reviewed_by=payload.get("reviewed_by", "agent:review"),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path == "/api/review/reject-candidate":
        _require_fields(payload, "candidate_id")
        with _open_operations() as operations:
            response = operations.reject_candidate(
                candidate_id=payload["candidate_id"],
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/evolution/snapshot-concept/"):
        concept_id = parsed.path.rsplit("/", 1)[-1]
        with _open_operations() as operations:
            response = operations.build_concept_timeline(concept_id)
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/evolution/build-timeline/"):
        concept_id = parsed.path.rsplit("/", 1)[-1]
        bucket_size = payload.get("bucket_size", "yearly")
        with _open_operations() as operations:
            response = operations.build_concept_timeline_bucketed(concept_id, bucket_size=bucket_size)
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path == "/api/evolution/cluster-conflicts":
        with _open_operations() as operations:
            response = operations.cluster_claim_conflicts(concept_id=payload.get("concept_id"))
        return 200, "application/json", json.dumps(response).encode("utf-8")
    if parsed.path.startswith("/api/prepare/papers/") and parsed.path.endswith("/output"):
        paper_id = parsed.path.split("/")[4]
        with _open_operations() as operations:
            response = operations.prepare_paper_for_output(
                paper_id,
                apply=bool(payload.get("apply", False)),
            )
        return 200, "application/json", json.dumps(response).encode("utf-8")
    raise KeyError(path)


def _source_pdf_status(paper, artifacts) -> dict:
    acquisition = None
    for artifact in artifacts:
        if artifact.artifact_type == "source_pdf_acquisition":
            acquisition = json.loads(artifact.metadata_json or "{}")
            break
    return {
        "available": bool(paper.pdf_path),
        "path": paper.pdf_path,
        "acquisition": acquisition,
    }
