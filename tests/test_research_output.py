from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rks.service import dispatch_get_request


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


def ingest_paper(tmp_path: Path, filename: str, text: str) -> str:
    pdf_path = tmp_path / filename
    pdf_path.write_bytes(("\n".join(["%PDF-1.4", text]) + "\n").encode("utf-8"))
    result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["id"]


def import_claims(tmp_path: Path, paper_id: str, claims: list[dict]) -> list[dict]:
    claims_path = tmp_path / f"{paper_id}-claims.json"
    claims_path.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    result = run_cli("import", "claims", paper_id, str(claims_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)


class ResearchOutputTest(unittest.TestCase):
    def test_output_surfaces_for_answer_brief_disagreements_and_opportunities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            paper_1 = ingest_paper(
                tmp_path,
                "paper-1.pdf",
                "We propose Sparse Attention. Sparse Attention improves translation accuracy on WMT14.",
            )
            paper_2 = ingest_paper(
                tmp_path,
                "paper-2.pdf",
                "We propose Sparse Attention. Sparse Attention improves translation accuracy on IWSLT.",
            )
            paper_3 = ingest_paper(
                tmp_path,
                "paper-3.pdf",
                "Sparse Attention does not improve translation accuracy on WMT14.",
            )

            claims_1 = import_claims(
                tmp_path,
                paper_1,
                [
                    {
                        "text": "Sparse Attention improves translation accuracy on WMT14.",
                        "predicate": "improves",
                        "object_text": "translation accuracy",
                        "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                        "evidence": {"paper_id": paper_1},
                        "confidence": 0.91,
                    }
                ],
            )
            import_claims(
                tmp_path,
                paper_2,
                [
                    {
                        "text": "Sparse Attention improves translation accuracy on IWSLT.",
                        "predicate": "improves",
                        "object_text": "translation accuracy",
                        "context": {"subject_text": "Sparse Attention", "dataset": "IWSLT"},
                        "evidence": {"paper_id": paper_2},
                        "confidence": 0.87,
                    }
                ],
            )
            claims_3 = import_claims(
                tmp_path,
                paper_3,
                [
                    {
                        "text": "Sparse Attention does not improve translation accuracy on WMT14.",
                        "predicate": "improves",
                        "object_text": "translation accuracy",
                        "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                        "evidence": {"paper_id": paper_3},
                        "confidence": 0.73,
                    }
                ],
            )

            self.assertEqual(run_cli("extract", "methods", paper_1, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("extract", "datasets", paper_1, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("extract", "datasets", paper_2, cwd=tmp_path).returncode, 0)

            promote_result = run_cli(
                "review",
                "promote-claim-relation",
                claims_1[0]["id"],
                "contradicts",
                claims_3[0]["id"],
                "--reviewed-by",
                "agent:test",
                "--note",
                "verified for output test",
                cwd=tmp_path,
            )
            self.assertEqual(promote_result.returncode, 0, promote_result.stderr)

            answer_result = run_cli("output", "answer", "Sparse Attention benchmark outlook", cwd=tmp_path)
            self.assertEqual(answer_result.returncode, 0, answer_result.stderr)
            answer_payload = json.loads(answer_result.stdout)
            self.assertIn("answer", answer_payload)
            self.assertGreaterEqual(len(answer_payload["supporting_claims"]), 1)
            self.assertGreaterEqual(len(answer_payload["disagreements"]), 1)
            self.assertGreaterEqual(len(answer_payload["next_steps"]), 1)

            brief_result = run_cli("output", "brief", "Sparse Attention", cwd=tmp_path)
            self.assertEqual(brief_result.returncode, 0, brief_result.stderr)
            brief_payload = json.loads(brief_result.stdout)
            self.assertIn("overview", brief_payload)
            self.assertGreaterEqual(len(brief_payload["key_claims"]), 1)
            self.assertGreaterEqual(len(brief_payload["methods"]), 1)
            self.assertGreaterEqual(len(brief_payload["datasets"]), 1)

            disagreements_result = run_cli("output", "disagreements", "Sparse Attention", cwd=tmp_path)
            self.assertEqual(disagreements_result.returncode, 0, disagreements_result.stderr)
            disagreements_payload = json.loads(disagreements_result.stdout)
            self.assertGreaterEqual(len(disagreements_payload["disagreements"]), 1)
            self.assertEqual(disagreements_payload["disagreements"][0]["relation_type"], "contradicts")

            opportunities_result = run_cli("output", "opportunities", "Sparse Attention", cwd=tmp_path)
            self.assertEqual(opportunities_result.returncode, 0, opportunities_result.stderr)
            opportunities_payload = json.loads(opportunities_result.stdout)
            self.assertGreaterEqual(len(opportunities_payload["opportunities"]), 1)
            kinds = {item["kind"] for item in opportunities_payload["opportunities"]}
            self.assertIn("resolve_disagreement", kinds)

            previous_cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                _, _, answer_body = dispatch_get_request("/api/output/answer?q=Sparse%20Attention%20benchmark%20outlook")
                _, _, brief_body = dispatch_get_request("/api/output/brief?topic=Sparse%20Attention")
                _, _, disagreements_body = dispatch_get_request("/api/output/disagreements?topic=Sparse%20Attention")
                _, _, opportunities_body = dispatch_get_request("/api/output/opportunities?topic=Sparse%20Attention")
            finally:
                os.chdir(previous_cwd)

            self.assertIn("answer", json.loads(answer_body.decode("utf-8")))
            self.assertIn("overview", json.loads(brief_body.decode("utf-8")))
            self.assertGreaterEqual(len(json.loads(disagreements_body.decode("utf-8"))["disagreements"]), 1)
            self.assertGreaterEqual(len(json.loads(opportunities_body.decode("utf-8"))["opportunities"]), 1)


if __name__ == "__main__":
    unittest.main()
