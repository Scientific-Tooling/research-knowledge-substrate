from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._run_cli import run_cli

ROOT = Path(__file__).resolve().parents[1]


class QualityHardeningTest(unittest.TestCase):
    def test_text_artifact_preserves_offsets_and_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "quality-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Abstract\n"
                b"Transformers improve translation accuracy on WMT14.\n"
                b"Introduction\n"
                b"Sparse attention reduces memory cost in long-context decoding.\n"
                b"Results\n"
                b"Diffusion models improve image fidelity on ImageNet.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            show_result = run_cli("show", "paper", paper_id, cwd=tmp_path)
            self.assertEqual(show_result.returncode, 0, show_result.stderr)
            show_payload = json.loads(show_result.stdout)
            artifacts = {artifact["artifact_type"]: artifact for artifact in show_payload["artifacts"]}

            text_artifact = artifacts["extracted_text"]
            text_metadata = text_artifact["metadata"]
            self.assertEqual(text_metadata["extractor"], "pdf_stream_decoder")
            self.assertEqual(text_metadata["extractor_version"], "1.0")
            self.assertEqual(text_metadata["mode"], "pdf-extractor")
            self.assertEqual(text_metadata["lineage"]["paper_id"], paper_id)

            text_payload = json.loads(Path(text_artifact["path"]).read_text(encoding="utf-8"))
            paragraph_records = text_payload["paragraph_records"]
            self.assertGreaterEqual(len(paragraph_records), 3)
            self.assertEqual(paragraph_records[0]["char_start"], 0)
            self.assertEqual(text_payload["text"][paragraph_records[0]["char_start"] : paragraph_records[0]["char_end"]], paragraph_records[0]["text"])

            sections_payload = json.loads(Path(artifacts["sections"]["path"]).read_text(encoding="utf-8"))
            result_section = next(section for section in sections_payload["sections"] if section["name"] == "results")
            self.assertGreater(result_section["char_end"], result_section["char_start"])
            self.assertEqual(result_section["paragraphs"], ["Diffusion models improve image fidelity on ImageNet."])

    def test_claim_reruns_keep_ids_and_normalized_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "deterministic-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Abstract\n"
                b"Transformers improve translation accuracy on WMT14.\n"
                b"Results\n"
                b"Sparse attention reduces memory cost in long-context decoding.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            claims_fixture_path = tmp_path / "deterministic_claims.json"
            claims_fixture_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Transformers improve translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Transformers"},
                                "evidence": {"paper_id": paper_id},
                                "confidence": 0.9,
                            },
                            {
                                "text": "Sparse attention reduces memory cost in long-context decoding.",
                                "predicate": "reduces",
                                "object_text": "memory cost",
                                "context": {"subject_text": "Sparse attention"},
                                "evidence": {"paper_id": paper_id},
                                "confidence": 0.85,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            first_result = run_cli("import", "claims", paper_id, str(claims_fixture_path), cwd=tmp_path)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            first_claims = json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)

            second_result = run_cli("import", "claims", paper_id, str(claims_fixture_path), cwd=tmp_path)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second_claims = json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)

            self.assertEqual([claim["id"] for claim in first_claims], [claim["id"] for claim in second_claims])

    def test_storage_db_submodule_imports_without_circular_error(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-c", "import rks.storage.db as db; print(db.__name__)"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rks.storage.db", result.stdout.strip())

    def test_init_db_upgrades_legacy_datasets_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # RKS_DATA_DIR=tmp_path means db_path = tmp_path / "rks.sqlite3"
            db_path = tmp_path / "rks.sqlite3"

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()

            init_result = run_cli("init-db", cwd=tmp_path)
            self.assertEqual(init_result.returncode, 0, init_result.stderr)

            conn = sqlite3.connect(db_path)
            try:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(datasets)").fetchall()]
            finally:
                conn.close()
            self.assertIn("paper_id", columns)

    def test_batch_ingest_returns_nonzero_when_any_item_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(
                json.dumps([{"source_type": "pdf", "path": "missing.pdf"}], indent=2),
                encoding="utf-8",
            )

            result = run_cli("batch", "ingest", str(manifest_path), cwd=tmp_path)
            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 0)
            self.assertEqual(len(payload["failures"]), 1)

    def test_evaluate_baseline_passes_with_satisfied_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "baseline-pass.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Transformers improve translation accuracy on WMT14.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            claims_fixture_path = tmp_path / "baseline_claims.json"
            claims_fixture_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Transformers improve translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Transformers"},
                                "evidence": {"paper_id": paper_id, "extraction": "agent"},
                                "confidence": 0.9,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            import_result = run_cli("import", "claims", paper_id, str(claims_fixture_path), cwd=tmp_path)
            self.assertEqual(import_result.returncode, 0, import_result.stderr)

            spec_path = tmp_path / "quality-baseline.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "name": "minimal-pass",
                        "checks": {
                            "min_paper_count": 1,
                            "min_total_claims": 1,
                            "max_zero_claim_rate": 0.0,
                            "min_extraction_mode_counts": {"agent": 1},
                            "per_paper_min_claims": {paper_id: 1},
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = run_cli("evaluate", "baseline", str(spec_path), cwd=tmp_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["passed"])
            self.assertEqual(payload["failed_check_count"], 0)

    def test_evaluate_baseline_returns_nonzero_on_failed_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "baseline-fail.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Transformers improve translation accuracy on WMT14.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)

            spec_path = tmp_path / "quality-baseline.json"
            spec_path.write_text(
                json.dumps({"checks": {"min_total_claims": 1}}, indent=2),
                encoding="utf-8",
            )

            result = run_cli("evaluate", "baseline", str(spec_path), cwd=tmp_path)
            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["passed"])
            self.assertGreaterEqual(payload["failed_check_count"], 1)


if __name__ == "__main__":
    unittest.main()
