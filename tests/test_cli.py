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


class CliSmokeTest(unittest.TestCase):
    def test_init_db_and_ingest_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "example-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Transformers improve translation accuracy on WMT14.\n"
                b"Diffusion models reduce image artifacts in generation.\n"
            )

            init_result = run_cli("init-db", cwd=tmp_path)
            self.assertEqual(init_result.returncode, 0, init_result.stderr)

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)

            payload = json.loads(ingest_result.stdout)
            self.assertEqual(payload["id"], "p_000001")
            self.assertEqual(payload["title"], "example-paper")
            self.assertIsNotNone(payload["text_artifact_id"])

            show_result = run_cli("show", "paper", payload["id"], cwd=tmp_path)
            self.assertEqual(show_result.returncode, 0, show_result.stderr)

            show_payload = json.loads(show_result.stdout)
            self.assertEqual(show_payload["id"], payload["id"])
            artifact_types = [artifact["artifact_type"] for artifact in show_payload["artifacts"]]
            self.assertIn("source_pdf", artifact_types)
            self.assertIn("extracted_text", artifact_types)
            self.assertIn("sections", artifact_types)
            self.assertEqual(show_payload["notes"], [])

            note_result = run_cli(
                "note",
                "add",
                "paper",
                payload["id"],
                "--content",
                "Focus on benchmark setup",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(note_result.returncode, 0, note_result.stderr)
            note_payload = json.loads(note_result.stdout)
            self.assertEqual(note_payload["target_id"], payload["id"])
            self.assertEqual(note_payload["created_by"], "human:test")

            notes_result = run_cli("note", "list", "paper", payload["id"], cwd=tmp_path)
            self.assertEqual(notes_result.returncode, 0, notes_result.stderr)
            notes_payload = json.loads(notes_result.stdout)
            self.assertEqual(len(notes_payload), 1)
            self.assertEqual(notes_payload[0]["content"], "Focus on benchmark setup")

            extract_claims_result = run_cli("extract", "claims", payload["id"], cwd=tmp_path)
            self.assertEqual(extract_claims_result.returncode, 0, extract_claims_result.stderr)
            extract_claims_payload = json.loads(extract_claims_result.stdout)
            self.assertGreaterEqual(extract_claims_payload["claim_count"], 1)

            rerun_claims_result = run_cli("extract", "claims", payload["id"], cwd=tmp_path)
            self.assertEqual(rerun_claims_result.returncode, 0, rerun_claims_result.stderr)

            claims_result = run_cli("claims", payload["id"], cwd=tmp_path)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            claims_payload = json.loads(claims_result.stdout)
            self.assertEqual(len(claims_payload), 2)
            self.assertEqual(claims_payload[0]["subject"], "Transformer")
            self.assertIn(claims_payload[0]["predicate"], {"supports", "improves"})
            self.assertIn("section", claims_payload[0]["evidence"])

            concepts_result = run_cli("concepts", payload["id"], cwd=tmp_path)
            self.assertEqual(concepts_result.returncode, 0, concepts_result.stderr)
            concepts_payload = json.loads(concepts_result.stdout)
            concept_names = [concept["name"] for concept in concepts_payload]
            self.assertIn("Transformer", concept_names)
            self.assertIn("Diffusion Model", concept_names)

            query_result = run_cli("query", "claims-about", "Transformer", cwd=tmp_path)
            self.assertEqual(query_result.returncode, 0, query_result.stderr)
            query_payload = json.loads(query_result.stdout)
            self.assertEqual(query_payload["concept"]["name"], "Transformer")
            self.assertEqual(len(query_payload["claims"]), 1)

            claim_id = claims_payload[0]["id"]
            supporting_result = run_cli("query", "papers-supporting", claim_id, cwd=tmp_path)
            self.assertEqual(supporting_result.returncode, 0, supporting_result.stderr)
            supporting_payload = json.loads(supporting_result.stdout)
            self.assertEqual(supporting_payload["papers"][0]["id"], payload["id"])

            show_claim_result = run_cli("show", "claim", claim_id, cwd=tmp_path)
            self.assertEqual(show_claim_result.returncode, 0, show_claim_result.stderr)
            show_claim_payload = json.loads(show_claim_result.stdout)
            self.assertEqual(show_claim_payload["subject"], "Transformer")
            self.assertGreaterEqual(len(show_claim_payload["edges"]), 2)
            self.assertIn("section", show_claim_payload["evidence"])

            search_result = run_cli("search", "Transformer", cwd=tmp_path)
            self.assertEqual(search_result.returncode, 0, search_result.stderr)
            search_payload = json.loads(search_result.stdout)
            self.assertGreaterEqual(len(search_payload["claims"]), 1)
            self.assertGreaterEqual(len(search_payload["concepts"]), 1)

            final_show_result = run_cli("show", "paper", payload["id"], cwd=tmp_path)
            self.assertEqual(final_show_result.returncode, 0, final_show_result.stderr)
            final_show_payload = json.loads(final_show_result.stdout)
            final_artifact_types = [artifact["artifact_type"] for artifact in final_show_payload["artifacts"]]
            self.assertEqual(final_artifact_types.count("structured_claims"), 1)
            self.assertEqual(final_artifact_types.count("claim_candidates"), 1)
            self.assertEqual(final_artifact_types.count("normalized_claims"), 1)
            self.assertEqual(len(final_show_payload["notes"]), 1)


if __name__ == "__main__":
    unittest.main()
