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
    env["RKS_DATA_DIR"] = str(cwd)
    return subprocess.run(
        [sys.executable, "-m", "rks", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class SummaryModeTest(unittest.TestCase):
    def test_summary_agent_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "summary-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Transformers improve translation accuracy on WMT14.\n"
                b"Diffusion models reduce image artifacts in generation.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            request_result = run_cli("summarize", "paper", paper_id, "--mode", "agent", cwd=tmp_path)
            self.assertEqual(request_result.returncode, 0, request_result.stderr)
            request_payload = json.loads(request_result.stdout)
            self.assertEqual(request_payload["artifact_type"], "agent_summary_request")

            summary_path = tmp_path / "agent_summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "summary": "Transformers and diffusion models are the central techniques in this paper.",
                        "evidence_claim_ids": ["c_000001"],
                        "open_questions": ["How well does the result generalize?"],
                    }
                ),
                encoding="utf-8",
            )
            import_result = run_cli("import", "summary", paper_id, str(summary_path), cwd=tmp_path)
            self.assertEqual(import_result.returncode, 0, import_result.stderr)
            import_payload = json.loads(import_result.stdout)
            self.assertIn("summary", import_payload)


if __name__ == "__main__":
    unittest.main()
