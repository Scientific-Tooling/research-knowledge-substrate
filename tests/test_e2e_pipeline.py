"""End-to-end pipeline test: ingest → extract (agent mode) → query → output → eval claims.

All extraction uses the agent dual-track path: the test supplies pre-seeded
fixture JSON instead of making real LLM calls, so this runs in CI without any
API keys.  The full sequence exercises every major stage:

    ingest pdf → import text → import claims → concepts →
    query claims-about → output answer → evaluate claims

Coverage goal (roadmap P0-2): verify that the complete pipeline produces
grounded, queryable, and evaluatable state from a single ingested document.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

_PAPER_TEXT = (
    "Transformers improve translation accuracy on WMT14. "
    "The attention mechanism allows the model to focus on relevant source tokens. "
    "We report a BLEU score of 28.4 on the English-to-German translation task."
)

_AGENT_TEXT_RESULT = {
    "text": _PAPER_TEXT,
    "paragraphs": [_PAPER_TEXT],
    "warnings": [],
}

_AGENT_CLAIMS_RESULT = {
    "claims": [
        {
            "text": "Transformers improve translation accuracy on WMT14.",
            "predicate": "improves",
            "object_text": "translation accuracy",
            "context": {
                "subject_text": "Transformers",
                "dataset": "WMT14",
                "section": "abstract",
            },
            "evidence": {"extraction": "agent"},
            "confidence": 0.92,
        },
        {
            "text": "The attention mechanism allows the model to focus on relevant source tokens.",
            "predicate": "allows",
            "object_text": "focus on relevant source tokens",
            "context": {
                "subject_text": "attention mechanism",
                "section": "method",
            },
            "evidence": {"extraction": "agent"},
            "confidence": 0.88,
        },
    ]
}

# Golden set used by the evaluate-claims check (a strict subset of the above).
_GOLDEN_CLAIMS = [
    "Transformers improve translation accuracy on WMT14.",
]


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


class E2EPipelineTest(unittest.TestCase):
    """Full pipeline: ingest → extract (agent) → query → output → evaluate claims."""

    def test_ingest_extract_query_output_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # --- 1. Ingest a minimal PDF ---
            pdf_path = tmp / "sample_paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n" + _PAPER_TEXT.encode() + b"\n")

            ingest = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp)
            self.assertEqual(ingest.returncode, 0, ingest.stderr)
            paper_id = json.loads(ingest.stdout)["id"]
            self.assertTrue(paper_id.startswith("p_"), paper_id)

            # --- 2. Request text extraction (agent mode) ---
            text_req = run_cli("extract", "text", paper_id, "--mode", "agent", cwd=tmp)
            self.assertEqual(text_req.returncode, 0, text_req.stderr)
            text_req_payload = json.loads(text_req.stdout)
            self.assertEqual(text_req_payload["artifact_type"], "agent_text_request")

            # --- 3. Import pre-seeded text result ---
            text_result_path = tmp / "agent_text_result.json"
            text_result_path.write_text(json.dumps(_AGENT_TEXT_RESULT), encoding="utf-8")

            import_text = run_cli("import", "text", paper_id, str(text_result_path), cwd=tmp)
            self.assertEqual(import_text.returncode, 0, import_text.stderr)

            # --- 4. Request claims extraction (agent mode) ---
            claims_req = run_cli("extract", "claims", paper_id, "--mode", "agent", cwd=tmp)
            self.assertEqual(claims_req.returncode, 0, claims_req.stderr)
            claims_req_payload = json.loads(claims_req.stdout)
            self.assertEqual(claims_req_payload["artifact_type"], "agent_claims_request")
            task_id = claims_req_payload.get("task_id")

            # --- 5. Import pre-seeded claims result ---
            claims_result_path = tmp / "agent_claims_result.json"
            # Patch evidence with the real paper_id so foreign-key constraints pass.
            result_with_id = json.loads(json.dumps(_AGENT_CLAIMS_RESULT))
            for claim in result_with_id["claims"]:
                claim["evidence"]["paper_id"] = paper_id
            claims_result_path.write_text(json.dumps(result_with_id), encoding="utf-8")

            import_claims = run_cli("import", "claims", paper_id, str(claims_result_path), cwd=tmp)
            self.assertEqual(import_claims.returncode, 0, import_claims.stderr)
            import_claims_payload = json.loads(import_claims.stdout)
            self.assertEqual(import_claims_payload["claim_count"], 2)
            self.assertEqual(len(import_claims_payload["claim_ids"]), 2)

            # --- 6. Verify claims are persisted ---
            claims = run_cli("claims", paper_id, cwd=tmp)
            self.assertEqual(claims.returncode, 0, claims.stderr)
            claims_payload = json.loads(claims.stdout)
            self.assertEqual(len(claims_payload), 2)
            subjects = {c["subject"] for c in claims_payload}
            self.assertIn("Transformer", subjects)

            # --- 7. Verify task completed (agent path bookkeeping) ---
            if task_id:
                task_show = run_cli("tasks", "show", task_id, cwd=tmp)
                self.assertEqual(task_show.returncode, 0, task_show.stderr)
                task_payload = json.loads(task_show.stdout)
                self.assertEqual(task_payload["status"], "completed")

            # --- 8. Query the knowledge graph ---
            query = run_cli("query", "claims-about", "Transformer", cwd=tmp)
            self.assertEqual(query.returncode, 0, query.stderr)
            query_payload = json.loads(query.stdout)
            self.assertEqual(query_payload["concept"]["name"], "Transformer")
            self.assertGreaterEqual(len(query_payload["claims"]), 1)

            # --- 9. Generate a research output ---
            answer = run_cli(
                "output", "answer",
                "What does the graph say about Transformer?",
                cwd=tmp,
            )
            self.assertEqual(answer.returncode, 0, answer.stderr)
            answer_payload = json.loads(answer.stdout)
            self.assertIn("answer", answer_payload)

            # --- 10. Evaluate claims against golden set (P0-1 integration) ---
            golden_path = tmp / "golden.json"
            golden_path.write_text(json.dumps(_GOLDEN_CLAIMS), encoding="utf-8")

            eval_result = run_cli(
                "evaluate", "claims", paper_id,
                "--golden", str(golden_path),
                "--min-f1", "0.5",
                cwd=tmp,
            )
            self.assertEqual(eval_result.returncode, 0, eval_result.stderr)
            eval_payload = json.loads(eval_result.stdout)
            self.assertEqual(eval_payload["paper_id"], paper_id)
            self.assertEqual(eval_payload["golden_count"], 1)
            self.assertEqual(eval_payload["actual_count"], 2)
            self.assertGreater(eval_payload["f1"], 0.0)
            self.assertTrue(eval_payload["passed"])


if __name__ == "__main__":
    unittest.main()
