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


class AgentModeTest(unittest.TestCase):
    def test_agent_roundtrip_for_text_and_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "agent-paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nPlaceholder source text.\n")

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            text_request_result = run_cli("extract", "text", paper_id, "--mode", "agent", cwd=tmp_path)
            self.assertEqual(text_request_result.returncode, 0, text_request_result.stderr)
            text_request = json.loads(text_request_result.stdout)
            self.assertEqual(text_request["artifact_type"], "agent_text_request")

            agent_text_path = tmp_path / "agent_text_result.json"
            agent_text_path.write_text(
                json.dumps(
                    {
                        "text": "Transformers improve translation accuracy on WMT14.",
                        "paragraphs": ["Transformers improve translation accuracy on WMT14."],
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            import_text_result = run_cli("import", "text", paper_id, str(agent_text_path), cwd=tmp_path)
            self.assertEqual(import_text_result.returncode, 0, import_text_result.stderr)

            claims_request_result = run_cli("extract", "claims", paper_id, "--mode", "agent", cwd=tmp_path)
            self.assertEqual(claims_request_result.returncode, 0, claims_request_result.stderr)
            claims_request = json.loads(claims_request_result.stdout)
            self.assertEqual(claims_request["artifact_type"], "agent_claims_request")

            agent_claims_path = tmp_path / "agent_claims_result.json"
            agent_claims_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Transformers improve translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {
                                    "subject_text": "Transformers",
                                    "dataset": "WMT14",
                                },
                                "evidence": {"paper_id": paper_id, "extraction": "agent"},
                                "confidence": 0.92,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            import_claims_result = run_cli("import", "claims", paper_id, str(agent_claims_path), cwd=tmp_path)
            self.assertEqual(import_claims_result.returncode, 0, import_claims_result.stderr)

            claims_result = run_cli("claims", paper_id, cwd=tmp_path)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            claims_payload = json.loads(claims_result.stdout)
            self.assertEqual(len(claims_payload), 1)
            self.assertEqual(claims_payload[0]["subject"], "Transformer")

            query_result = run_cli("query", "claims-about", "Transformer", cwd=tmp_path)
            self.assertEqual(query_result.returncode, 0, query_result.stderr)
            query_payload = json.loads(query_result.stdout)
            self.assertEqual(query_payload["concept"]["name"], "Transformer")


if __name__ == "__main__":
    unittest.main()
