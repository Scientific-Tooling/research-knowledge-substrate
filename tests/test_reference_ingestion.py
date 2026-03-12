from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from rks.config import AppPaths
from rks.ingestion.reference import ingest_arxiv_reference, ingest_doi_reference
from rks.service import dispatch_get_request
from rks.storage import PaperRepository, connect_db, initialize_db


class _FakeProvider:
    def __init__(self, payload: dict):
        self.payload = payload

    def fetch(self, _identifier: str) -> dict:
        return self.payload


class ReferenceIngestionTest(unittest.TestCase):
    def test_reference_ingestion_downloads_source_pdf_and_exposes_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = AppPaths(
                root=root,
                data_dir=root / "data",
                papers_dir=root / "data" / "papers",
                artifacts_dir=root / "data" / "artifacts",
                db_path=root / "data" / "rks.sqlite3",
            )
            paths.data_dir.mkdir(parents=True, exist_ok=True)
            conn = connect_db(paths.db_path)
            initialize_db(conn)
            repo = PaperRepository(conn)

            paper = ingest_doi_reference(
                repo=repo,
                paths=paths,
                doi="10.1000/example",
                provider=_FakeProvider(
                    {
                        "title": "Example DOI Paper",
                        "abstract": "A short abstract for testing.",
                        "authors": ["Ada Lovelace"],
                        "year": 2024,
                        "venue": "TestConf",
                        "doi": "10.1000/example",
                        "arxiv_id": None,
                        "references": [],
                        "pdf_candidates": [{"url": "https://example.org/paper.pdf", "source": "test"}],
                        "raw": {"ok": True},
                    }
                ),
                downloader=lambda url: b"%PDF-1.4\nDownloaded from " + url.encode("utf-8"),
            )

            artifacts = repo.get_artifacts_for_paper(paper.id)
            artifact_types = {artifact.artifact_type for artifact in artifacts}
            self.assertIn("source_pdf", artifact_types)
            self.assertIn("source_pdf_acquisition", artifact_types)
            self.assertTrue(Path(paper.pdf_path).exists())

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                _, _, status_body = dispatch_get_request(f"/api/status/{paper.id}")
            finally:
                os.chdir(previous_cwd)
            status_payload = json.loads(status_body.decode("utf-8"))
            self.assertTrue(status_payload["source_pdf"]["available"])
            self.assertEqual(status_payload["source_pdf"]["acquisition"]["status"], "downloaded")
            self.assertEqual(
                status_payload["source_pdf"]["acquisition"]["downloaded_from"],
                "https://example.org/paper.pdf",
            )
            conn.close()

    def test_reference_ingestion_records_skipped_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = AppPaths(
                root=root,
                data_dir=root / "data",
                papers_dir=root / "data" / "papers",
                artifacts_dir=root / "data" / "artifacts",
                db_path=root / "data" / "rks.sqlite3",
            )
            paths.data_dir.mkdir(parents=True, exist_ok=True)
            conn = connect_db(paths.db_path)
            initialize_db(conn)
            repo = PaperRepository(conn)

            paper = ingest_arxiv_reference(
                repo=repo,
                paths=paths,
                arxiv_id="1234.5678",
                provider=_FakeProvider(
                    {
                        "title": "Example arXiv Paper",
                        "abstract": None,
                        "authors": ["Grace Hopper"],
                        "year": 2025,
                        "venue": "arXiv",
                        "doi": None,
                        "arxiv_id": "1234.5678",
                        "references": [],
                        "pdf_candidates": [{"url": "https://arxiv.org/pdf/1234.5678.pdf", "source": "arxiv_pdf"}],
                        "raw": "<xml />",
                    }
                ),
                acquire_pdf=False,
            )

            artifacts = repo.get_artifacts_for_paper(paper.id)
            acquisition_artifact = next(
                artifact for artifact in artifacts if artifact.artifact_type == "source_pdf_acquisition"
            )
            payload = json.loads(acquisition_artifact.metadata_json)
            self.assertEqual(payload["status"], "skipped")
            self.assertFalse(repo.get_paper(paper.id).pdf_path)
            conn.close()


if __name__ == "__main__":
    unittest.main()
