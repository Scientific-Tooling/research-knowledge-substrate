from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rks.service import dispatch_post_request


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


class AgentWorkflowTest(unittest.TestCase):
    def test_task_queue_status_and_agent_schema_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "workflow-paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nPlaceholder source text.\n")

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            claims_request_result = run_cli("extract", "claims", paper_id, "--mode", "agent", cwd=tmp_path)
            self.assertEqual(claims_request_result.returncode, 0, claims_request_result.stderr)
            claims_request = json.loads(claims_request_result.stdout)
            self.assertEqual(claims_request["schema_version"], "claims.v1")
            self.assertTrue(claims_request["task_id"].startswith("t_"))

            tasks_list = json.loads(run_cli("tasks", "list", "--paper-id", paper_id, cwd=tmp_path).stdout)
            self.assertEqual(tasks_list[0]["status"], "queued")
            self.assertEqual(tasks_list[0]["schema_version"], "claims.v1")

            agent_claims_path = tmp_path / "agent_claims_result.json"
            agent_claims_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Sparse Attention improves translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                                "evidence": {"paper_id": paper_id},
                                "confidence": 0.92,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            import_result = run_cli("import", "claims", paper_id, str(agent_claims_path), cwd=tmp_path)
            self.assertEqual(import_result.returncode, 0, import_result.stderr)

            task_detail = json.loads(run_cli("tasks", "show", claims_request["task_id"], cwd=tmp_path).stdout)
            self.assertEqual(task_detail["status"], "completed")
            self.assertIsNotNone(task_detail["result_artifact_id"])

            summary_request = json.loads(run_cli("summarize", "paper", paper_id, "--mode", "agent", cwd=tmp_path).stdout)
            failed_task = json.loads(run_cli("tasks", "fail", summary_request["task_id"], "agent timeout", cwd=tmp_path).stdout)
            self.assertEqual(failed_task["status"], "failed")
            self.assertEqual(failed_task["error"]["message"], "agent timeout")

            status_payload = json.loads(run_cli("status", "paper", paper_id, cwd=tmp_path).stdout)
            self.assertTrue(status_payload["stages"]["claims"])
            self.assertEqual(status_payload["task_summary"]["completed"], 1)
            self.assertEqual(status_payload["task_summary"]["failed"], 1)
            self.assertIn("agent_execution_reports", status_payload["artifacts"])
            self.assertEqual(len(status_payload["agent_reports"]), 2)
            self.assertEqual(status_payload["agent_reports"][0]["current_status"], "completed")
            self.assertEqual(status_payload["agent_reports"][1]["current_status"], "failed")
            self.assertEqual(status_payload["recovery_guidance"][0]["status"], "failed")
            self.assertIn(f"rks summarize paper {paper_id} --mode agent", status_payload["recovery_guidance"][0]["commands"])

            prepare_plan = json.loads(run_cli("prepare", "paper-output", paper_id, cwd=tmp_path).stdout)
            self.assertFalse(prepare_plan["ready_before"])
            self.assertTrue(any(action["code"] == "extract_methods" for action in prepare_plan["planned_actions"]))

            prepare_apply = json.loads(run_cli("prepare", "paper-output", paper_id, "--apply", cwd=tmp_path).stdout)
            self.assertTrue(prepare_apply["ready_after"])
            executed_codes = {action["code"] for action in prepare_apply["executed_actions"]}
            self.assertIn("extract_methods", executed_codes)
            self.assertIn("extract_datasets", executed_codes)
            self.assertIn("summarize_paper", executed_codes)

            previous_cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                _, _, prepare_body = dispatch_post_request(
                    f"/api/prepare/papers/{paper_id}/output",
                    json.dumps({"apply": False}).encode("utf-8"),
                )
            finally:
                os.chdir(previous_cwd)
            prepare_http_payload = json.loads(prepare_body.decode("utf-8"))
            self.assertEqual(prepare_http_payload["goal"], "output")
            self.assertTrue(prepare_http_payload["ready_before"])

    def test_batch_ingest_and_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            first_pdf = tmp_path / "batch-1.pdf"
            second_pdf = tmp_path / "batch-2.pdf"
            first_pdf.write_bytes(b"%PDF-1.4\nTransformers improve translation accuracy on WMT14.\n")
            second_pdf.write_bytes(b"%PDF-1.4\nDiffusion models reduce image artifacts on ImageNet.\n")

            ingest_manifest = tmp_path / "ingest.json"
            ingest_manifest.write_text(
                json.dumps(
                    [
                        {"source_type": "pdf", "path": "batch-1.pdf"},
                        {"source_type": "pdf", "path": "batch-2.pdf"},
                    ]
                ),
                encoding="utf-8",
            )
            ingest_result = run_cli("batch", "ingest", str(ingest_manifest), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            ingest_payload = json.loads(ingest_result.stdout)
            self.assertEqual(ingest_payload["count"], 2)
            self.assertEqual(ingest_payload["audit"]["success_count"], 2)
            self.assertEqual(ingest_payload["audit"]["failure_count"], 0)

            paper_ids = [paper["id"] for paper in ingest_payload["papers"]]
            extract_manifest = tmp_path / "extract.json"
            extract_manifest.write_text(json.dumps([{"paper_id": paper_id} for paper_id in paper_ids]), encoding="utf-8")

            extract_result = run_cli("batch", "extract", "claims", str(extract_manifest), cwd=tmp_path)
            self.assertEqual(extract_result.returncode, 0, extract_result.stderr)
            extract_payload = json.loads(extract_result.stdout)
            self.assertEqual(extract_payload["count"], 2)
            self.assertTrue(all(result["claim_count"] >= 1 for result in extract_payload["results"]))
            self.assertEqual(extract_payload["audit"]["success_count"], 2)
            self.assertGreaterEqual(extract_payload["audit"]["total_claim_count"], 2)

            output_manifest = tmp_path / "output.json"
            output_manifest.write_text(
                json.dumps(
                    [
                        {"question": "What does the graph say about Transformer?"},
                        {"question": "What does the graph say about Diffusion Model?"},
                    ]
                ),
                encoding="utf-8",
            )
            output_result = run_cli("batch", "output", "answer", str(output_manifest), cwd=tmp_path)
            self.assertEqual(output_result.returncode, 0, output_result.stderr)
            output_payload = json.loads(output_result.stdout)
            self.assertEqual(output_payload["count"], 2)
            self.assertEqual(output_payload["audit"]["success_count"], 2)
            self.assertEqual(output_payload["audit"]["failure_count"], 0)
            self.assertEqual(len(output_payload["results"]), 2)


if __name__ == "__main__":
    unittest.main()
