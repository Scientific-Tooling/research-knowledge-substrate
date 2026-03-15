from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
            self.assertEqual(text_metadata["mode"], "heuristic")
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

            first_result = run_cli("extract", "claims", paper_id, cwd=tmp_path)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            first_claims = json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)

            second_result = run_cli("extract", "claims", paper_id, cwd=tmp_path)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second_claims = json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)

            self.assertEqual([claim["id"] for claim in first_claims], [claim["id"] for claim in second_claims])
            evidence = first_claims[0]["evidence"]
            self.assertIn("snippet", evidence)
            self.assertIn("char_start", evidence)
            self.assertIn("char_end", evidence)
            self.assertEqual(evidence["extractor_version"], "1.1")


if __name__ == "__main__":
    unittest.main()
