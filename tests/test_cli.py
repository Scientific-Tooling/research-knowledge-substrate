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
                b"Our results show the method improves translation accuracy.\n"
                b"The system reduces training cost in our evaluation.\n"
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

            extract_claims_result = run_cli("extract", "claims", payload["id"], cwd=tmp_path)
            self.assertEqual(extract_claims_result.returncode, 0, extract_claims_result.stderr)
            extract_claims_payload = json.loads(extract_claims_result.stdout)
            self.assertGreaterEqual(extract_claims_payload["claim_count"], 1)

            claims_result = run_cli("claims", payload["id"], cwd=tmp_path)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            claims_payload = json.loads(claims_result.stdout)
            self.assertGreaterEqual(len(claims_payload), 1)
            self.assertIn(claims_payload[0]["predicate"], {"supports", "improves"})


if __name__ == "__main__":
    unittest.main()
