from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from rks.config import load_paths
from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    DatasetRepository,
    EmbeddingRepository,
    EdgeRepository,
    MethodRepository,
    PaperRepository,
    TaskRepository,
    connect_db,
    initialize_db,
)


def serve_http(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), _build_handler())
    server.serve_forever()


def _build_handler():
    class RksHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            try:
                status_code, content_type, body = dispatch_get_request(self.path)
            except KeyError:
                self.send_error(404, "Not found")
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
            "claims": ClaimRepository(self.conn),
            "concepts": ConceptRepository(self.conn),
            "edges": EdgeRepository(self.conn),
            "methods": MethodRepository(self.conn),
            "datasets": DatasetRepository(self.conn),
            "embeddings": EmbeddingRepository(self.conn),
            "tasks": TaskRepository(self.conn),
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
    if parsed.path == "/api/search":
        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0]
        mode = params.get("mode", ["hybrid"])[0]
        with _open_query_service() as query_service:
            payload = query_service.search(query, mode=mode)
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/papers/"):
        paper_id = parsed.path.rsplit("/", 1)[-1]
        with _open_repositories() as repos:
            paper = repos["papers"].get_paper(paper_id)
            artifacts = repos["papers"].get_artifacts_for_paper(paper_id)
            payload = {
                "id": paper.id,
                "title": paper.title,
                "source_type": paper.source_type,
                "source_ref": paper.source_ref,
                "artifacts": [artifact.artifact_type for artifact in artifacts],
            }
        return 200, "application/json", json.dumps(payload).encode("utf-8")
    if parsed.path.startswith("/api/status/"):
        paper_id = parsed.path.rsplit("/", 1)[-1]
        with _open_repositories() as repos:
            artifacts = repos["papers"].get_artifacts_for_paper(paper_id)
            tasks = repos["tasks"].list_tasks(paper_id=paper_id)
            payload = {
                "paper_id": paper_id,
                "artifacts": [artifact.artifact_type for artifact in artifacts],
                "tasks": [{"id": task.id, "task_type": task.task_type, "status": task.status} for task in tasks],
            }
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
