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


class SectionArtifactTest(unittest.TestCase):
    def test_section_detection_and_section_aware_claim_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "sectioned-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Abstract\n"
                b"Transformers improve translation accuracy on WMT14.\n"
                b"Experiments\n"
                b"Diffusion models reduce image artifacts in generation.\n"
            )

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            show_result = run_cli("show", "paper", paper_id, cwd=tmp_path)
            self.assertEqual(show_result.returncode, 0, show_result.stderr)
            show_payload = json.loads(show_result.stdout)
            artifacts = {artifact["artifact_type"]: artifact for artifact in show_payload["artifacts"]}
            self.assertIn("sections", artifacts)

            sections_path = Path(artifacts["sections"]["path"])
            sections_payload = json.loads(sections_path.read_text(encoding="utf-8"))
            section_names = [section["name"] for section in sections_payload["sections"]]
            self.assertIn("abstract", section_names)
            self.assertIn("experiments", section_names)

            claims_fixture_path = tmp_path / "section_claims.json"
            claims_fixture_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Transformers improve translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Transformers"},
                                "evidence": {"paper_id": paper_id, "section": "abstract"},
                                "confidence": 0.9,
                            },
                            {
                                "text": "Diffusion models reduce image artifacts in generation.",
                                "predicate": "reduces",
                                "object_text": "image artifacts",
                                "context": {"subject_text": "Diffusion Model"},
                                "evidence": {"paper_id": paper_id, "section": "experiments"},
                                "confidence": 0.85,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            import_claims_result = run_cli("import", "claims", paper_id, str(claims_fixture_path), cwd=tmp_path)
            self.assertEqual(import_claims_result.returncode, 0, import_claims_result.stderr)

            claims_result = run_cli("claims", paper_id, cwd=tmp_path)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            claims_payload = json.loads(claims_result.stdout)
            evidence_sections = {claim["evidence"]["section"] for claim in claims_payload}
            self.assertIn("abstract", evidence_sections)
            self.assertIn("experiments", evidence_sections)


if __name__ == "__main__":
    unittest.main()
