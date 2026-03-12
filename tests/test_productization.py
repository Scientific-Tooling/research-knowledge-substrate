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


class ProductizationTest(unittest.TestCase):
    def test_config_migrate_and_graph_snapshot_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            pdf_path = source / "product-paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nTransformers improve translation accuracy on WMT14.\n")

            config_init = run_cli("config", "init", cwd=source)
            self.assertEqual(config_init.returncode, 0, config_init.stderr)
            self.assertTrue((source / "rks.json").exists())

            config_show = run_cli("config", "show", cwd=source)
            self.assertEqual(config_show.returncode, 0, config_show.stderr)
            config_payload = json.loads(config_show.stdout)
            self.assertTrue(config_payload["data_dir"].endswith("data"))

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=source)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]
            self.assertEqual(run_cli("extract", "claims", paper_id, cwd=source).returncode, 0)

            migrate_result = run_cli("migrate", cwd=source)
            self.assertEqual(migrate_result.returncode, 0, migrate_result.stderr)
            migrate_payload = json.loads(migrate_result.stdout)
            self.assertEqual(migrate_payload["current_version"], "0001_init.sql")

            snapshot_path = source / "snapshot.json"
            export_result = run_cli("export", "graph", str(snapshot_path), cwd=source)
            self.assertEqual(export_result.returncode, 0, export_result.stderr)
            self.assertTrue(snapshot_path.exists())

            import_result = run_cli("import", "graph", str(snapshot_path), cwd=target)
            self.assertEqual(import_result.returncode, 0, import_result.stderr)

            show_result = run_cli("show", "paper", paper_id, cwd=target)
            self.assertEqual(show_result.returncode, 0, show_result.stderr)
            show_payload = json.loads(show_result.stdout)
            self.assertEqual(show_payload["id"], paper_id)

            claims_result = run_cli("claims", paper_id, cwd=target)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            self.assertGreaterEqual(len(json.loads(claims_result.stdout)), 1)

    def test_service_api_and_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "service-paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nTransformers improve translation accuracy on WMT14.\n")

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]
            self.assertEqual(run_cli("extract", "claims", paper_id, cwd=tmp_path).returncode, 0)

            previous_cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                _, _, health_body = dispatch_get_request("/health")
                self.assertEqual(json.loads(health_body.decode("utf-8"))["status"], "ok")

                _, _, search_body = dispatch_get_request("/api/search?q=Transformer&mode=hybrid")
                search_payload = json.loads(search_body.decode("utf-8"))
                self.assertTrue(search_payload["claims"] or search_payload["semantic_matches"])

                _, _, status_body = dispatch_get_request(f"/api/status/{paper_id}")
                status_payload = json.loads(status_body.decode("utf-8"))
                self.assertIn("structured_claims", status_payload["artifacts"])

                _, _, ui_body = dispatch_get_request("/")
                self.assertIn("RKS Workspace", ui_body.decode("utf-8"))
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
