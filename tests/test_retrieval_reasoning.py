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


def ingest_placeholder_paper(tmp_path: Path, filename: str) -> str:
    pdf_path = tmp_path / filename
    pdf_path.write_bytes(b"%PDF-1.4\nPlaceholder text.\n")
    ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
    assert ingest_result.returncode == 0, ingest_result.stderr
    return json.loads(ingest_result.stdout)["id"]


def import_claims(tmp_path: Path, paper_id: str, claims: list[dict]) -> list[dict]:
    claims_path = tmp_path / f"{paper_id}-claims.json"
    claims_path.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    result = run_cli("import", "claims", paper_id, str(claims_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)


class RetrievalReasoningTest(unittest.TestCase):
    def test_semantic_search_claim_relations_and_evidence_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            paper_1 = ingest_placeholder_paper(tmp_path, "paper-1.pdf")
            paper_2 = ingest_placeholder_paper(tmp_path, "paper-2.pdf")
            paper_3 = ingest_placeholder_paper(tmp_path, "paper-3.pdf")

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
                        "confidence": 0.9,
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
                        "confidence": 0.88,
                    }
                ],
            )
            import_claims(
                tmp_path,
                paper_3,
                [
                    {
                        "text": "Sparse Attention does not improve translation accuracy on WMT14.",
                        "predicate": "improves",
                        "object_text": "translation accuracy",
                        "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                        "evidence": {"paper_id": paper_3},
                        "confidence": 0.77,
                    }
                ],
            )

            anchor_claim_id = claims_1[0]["id"]

            semantic_search = run_cli("search", "translation quality benchmark", "--mode", "semantic", cwd=tmp_path)
            self.assertEqual(semantic_search.returncode, 0, semantic_search.stderr)
            semantic_payload = json.loads(semantic_search.stdout)
            self.assertEqual(semantic_payload["mode"], "semantic")
            self.assertGreaterEqual(len(semantic_payload["semantic_matches"]), 1)

            relations_result = run_cli("query", "claim-relations", anchor_claim_id, cwd=tmp_path)
            self.assertEqual(relations_result.returncode, 0, relations_result.stderr)
            relations_payload = json.loads(relations_result.stdout)
            relation_types = {relation["relation_type"] for relation in relations_payload["relations"]}
            self.assertIn("refines", relation_types)
            self.assertIn("contradicts", relation_types)

            evidence_result = run_cli("query", "evidence-for", "Sparse Attention", cwd=tmp_path)
            self.assertEqual(evidence_result.returncode, 0, evidence_result.stderr)
            evidence_payload = json.loads(evidence_result.stdout)
            self.assertEqual(evidence_payload["target_type"], "concept")
            self.assertEqual(len(evidence_payload["claims"]), 3)
            self.assertEqual(len(evidence_payload["papers"]), 3)

            summary_result = run_cli("summarize", "paper", paper_1, cwd=tmp_path)
            self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
            summary_payload = json.loads(summary_result.stdout)
            self.assertEqual(summary_payload["evidence_paper_ids"], [paper_1])
            self.assertGreaterEqual(len(summary_payload["citations"]), 1)


if __name__ == "__main__":
    unittest.main()
