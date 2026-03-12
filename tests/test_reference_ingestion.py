from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from rks.config import AppPaths
from rks.extraction import extract_claims_for_paper
from rks.ingestion.reference import ingest_arxiv_reference, ingest_doi_reference
from rks.query import QueryService
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    EdgeRepository,
    PaperRepository,
    connect_db,
    initialize_db,
)


class _FakeCrossrefProvider:
    def fetch(self, doi: str) -> dict:
        return {
            "title": "Transformer Scaling",
            "abstract": "Transformers improve translation accuracy on WMT14. Sparse attention reduces memory cost.",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "venue": "TestConf",
            "doi": doi,
            "arxiv_id": None,
            "raw": {"doi": doi},
        }


class _FakeArxivProvider:
    def fetch(self, arxiv_id: str) -> dict:
        return {
            "title": "Diffusion Systems",
            "abstract": "Diffusion models reduce image artifacts in generation.",
            "authors": ["Grace Hopper"],
            "year": 2025,
            "venue": "arXiv",
            "doi": None,
            "arxiv_id": arxiv_id,
            "raw": "<entry></entry>",
        }


class ReferenceIngestionTest(unittest.TestCase):
    def test_ingest_doi_and_arxiv_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = AppPaths(
                root=root,
                data_dir=root / "data",
                papers_dir=root / "data" / "papers",
                artifacts_dir=root / "data" / "artifacts",
                db_path=root / "data" / "rks.sqlite3",
            )
            conn = connect_db(paths.db_path)
            initialize_db(conn)

            papers = PaperRepository(conn)
            claims = ClaimRepository(conn)
            concepts = ConceptRepository(conn)
            edges = EdgeRepository(conn)

            doi_paper = ingest_doi_reference(
                repo=papers,
                paths=paths,
                doi="10.1000/test-doi",
                provider=_FakeCrossrefProvider(),
            )
            arxiv_paper = ingest_arxiv_reference(
                repo=papers,
                paths=paths,
                arxiv_id="2501.00001",
                provider=_FakeArxivProvider(),
            )

            self.assertEqual(doi_paper.source_type, "doi")
            self.assertEqual(arxiv_paper.source_type, "arxiv")
            self.assertIsNotNone(doi_paper.text_artifact_id)
            self.assertIsNotNone(arxiv_paper.text_artifact_id)

            doi_claims = extract_claims_for_paper(
                paths=paths,
                paper_repo=papers,
                claim_repo=claims,
                concept_repo=concepts,
                edge_repo=edges,
                paper_id=doi_paper.id,
            )
            self.assertGreaterEqual(len(doi_claims), 2)

            query = QueryService(
                papers=papers,
                claims=claims,
                concepts=concepts,
                edges=edges,
            )
            payload = query.claims_about("Transformer")
            self.assertEqual(payload["concept"]["name"], "Transformer")
            self.assertGreaterEqual(len(payload["claims"]), 1)

            metadata_path = root / "data" / "papers" / doi_paper.id / "metadata.json"
            self.assertTrue(metadata_path.exists())
            self.assertEqual(json.loads(metadata_path.read_text(encoding="utf-8"))["doi"], "10.1000/test-doi")

            conn.close()


if __name__ == "__main__":
    unittest.main()
