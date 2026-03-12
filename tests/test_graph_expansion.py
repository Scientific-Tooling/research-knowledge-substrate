from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rks.config import AppPaths
from rks.concepts.normalize import canonicalize_term
from rks.ingestion.reference import ingest_doi_reference
from rks.storage import ConceptRepository, EdgeRepository, PaperRepository, connect_db, initialize_db


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "rks", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class _FakeCrossrefWithReferences:
    def fetch(self, doi: str) -> dict:
        return {
            "title": "Sparse Attention Systems",
            "abstract": "Sparse Attention improves translation accuracy on WMT14.",
            "authors": ["Ada Lovelace"],
            "year": 2025,
            "venue": "TestConf",
            "doi": doi,
            "arxiv_id": None,
            "references": [
                {
                    "doi": "10.1000/previous-work",
                    "title": "Earlier Transformer Study",
                    "year": 2023,
                }
            ],
            "raw": {"doi": doi},
        }


class GraphExpansionTest(unittest.TestCase):
    def test_method_and_dataset_extraction_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "graph-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Abstract\n"
                b"We propose Sparse Attention.\n"
                b"Sparse Attention improves translation accuracy on WMT14.\n"
                b"Experiments\n"
                b"Sparse Attention reduces memory cost on WMT14.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            self.assertEqual(run_cli("extract", "claims", paper_id, cwd=tmp_path).returncode, 0)
            methods_result = run_cli("extract", "methods", paper_id, cwd=tmp_path)
            datasets_result = run_cli("extract", "datasets", paper_id, cwd=tmp_path)
            self.assertEqual(methods_result.returncode, 0, methods_result.stderr)
            self.assertEqual(datasets_result.returncode, 0, datasets_result.stderr)

            methods_payload = json.loads(run_cli("methods", paper_id, cwd=tmp_path).stdout)
            datasets_payload = json.loads(run_cli("datasets", paper_id, cwd=tmp_path).stdout)
            self.assertEqual(methods_payload[0]["name"], "Sparse Attention")
            self.assertEqual(datasets_payload[0]["name"], "WMT14")

            method_detail = json.loads(run_cli("show", "method", methods_payload[0]["id"], cwd=tmp_path).stdout)
            dataset_detail = json.loads(run_cli("show", "dataset", datasets_payload[0]["id"], cwd=tmp_path).stdout)
            self.assertIn("proposes", {edge["relation_type"] for edge in method_detail["edges"]})
            self.assertIn("evaluated_on", {edge["relation_type"] for edge in method_detail["edges"]})
            self.assertIn("uses", {edge["relation_type"] for edge in dataset_detail["edges"]})

            search_payload = json.loads(run_cli("search", "Sparse Attention", cwd=tmp_path).stdout)
            self.assertGreaterEqual(len(search_payload["methods"]), 1)
            self.assertGreaterEqual(len(search_payload["datasets"]), 1)

    def test_citation_ingestion_and_concept_hierarchy(self) -> None:
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
            edges = EdgeRepository(conn)
            concepts = ConceptRepository(conn)
            cited = papers.create_paper_from_reference(
                title="Earlier Transformer Study",
                abstract=None,
                authors=[],
                year=2023,
                venue="TestConf",
                doi="10.1000/previous-work",
                arxiv_id=None,
                source_type="doi",
                source_ref="10.1000/previous-work",
                pdf_path=None,
            )

            paper = ingest_doi_reference(
                repo=papers,
                paths=paths,
                doi="10.1000/current-work",
                provider=_FakeCrossrefWithReferences(),
            )
            paper_edges = edges.list_edges_for_object(paper.id)
            cite_edges = [edge for edge in paper_edges if edge.relation_type == "cites"]
            self.assertEqual(cite_edges[0].target_id, cited.id)

            citations_path = root / "data" / "papers" / paper.id / "citations.json"
            self.assertTrue(citations_path.exists())

            concept = concepts.get_or_create("Sparse Attention")
            parent = concepts.get_concept(concept.parent_concept_id)
            self.assertEqual(canonicalize_term(parent.name), "Attention")

            conn.close()


if __name__ == "__main__":
    unittest.main()
