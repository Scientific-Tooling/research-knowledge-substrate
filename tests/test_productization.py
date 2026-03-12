from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rks.service import dispatch_get_request, dispatch_post_request
from rks.agent_skills import list_bundled_skills
from rks.storage.db import _packaged_migration_files

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
    def test_packaged_skills_match_repository_skill_docs(self) -> None:
        bundled = {skill.name: skill.content for skill in list_bundled_skills()}
        repo_skills_dir = ROOT / "skills"
        repo_skill_paths = sorted(repo_skills_dir.glob("*/SKILL.md"))
        self.assertEqual(set(bundled), {path.parent.name for path in repo_skill_paths})

        for skill_path in repo_skill_paths:
            self.assertEqual(bundled[skill_path.parent.name], skill_path.read_text(encoding="utf-8"))

    def test_packaged_migrations_exist_for_distributions(self) -> None:
        packaged = _packaged_migration_files()
        self.assertEqual([path.name for path in packaged], ["0001_init.sql"])
        self.assertIn("CREATE TABLE IF NOT EXISTS papers", packaged[0].read_text(encoding="utf-8"))

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
            add_note_result = run_cli(
                "note",
                "add",
                "paper",
                paper_id,
                "--content",
                "Recheck baseline numbers before export",
                cwd=source,
            )
            self.assertEqual(add_note_result.returncode, 0, add_note_result.stderr)
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
            self.assertEqual(len(show_payload["notes"]), 1)
            self.assertEqual(show_payload["notes"][0]["content"], "Recheck baseline numbers before export")

            claims_result = run_cli("claims", paper_id, cwd=target)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            self.assertGreaterEqual(len(json.loads(claims_result.stdout)), 1)

    def test_service_api_and_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "service-paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nPlaceholder source text.\n")
            related_pdf_path = tmp_path / "service-paper-2.pdf"
            related_pdf_path.write_bytes(b"%PDF-1.4\nPlaceholder source text.\n")

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]
            related_ingest_result = run_cli("ingest", "pdf", str(related_pdf_path), cwd=tmp_path)
            self.assertEqual(related_ingest_result.returncode, 0, related_ingest_result.stderr)
            related_paper_id = json.loads(related_ingest_result.stdout)["id"]

            first_claims_path = tmp_path / "service-paper-claims.json"
            first_claims_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Sparse Attention improves translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                                "evidence": {"paper_id": paper_id},
                                "confidence": 0.91,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            second_claims_path = tmp_path / "service-paper-2-claims.json"
            second_claims_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Sparse Attention does not improve translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                                "evidence": {"paper_id": related_paper_id},
                                "confidence": 0.73,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(run_cli("import", "claims", paper_id, str(first_claims_path), cwd=tmp_path).returncode, 0)
            self.assertEqual(
                run_cli("import", "claims", related_paper_id, str(second_claims_path), cwd=tmp_path).returncode,
                0,
            )

            previous_cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                _, _, health_body = dispatch_get_request("/health")
                self.assertEqual(json.loads(health_body.decode("utf-8"))["status"], "ok")

                _, _, search_body = dispatch_get_request("/api/search?q=Sparse%20Attention&mode=hybrid")
                search_payload = json.loads(search_body.decode("utf-8"))
                self.assertTrue(search_payload["claims"] or search_payload["semantic_matches"])

                _, _, status_body = dispatch_get_request(f"/api/status/{paper_id}")
                status_payload = json.loads(status_body.decode("utf-8"))
                self.assertIn("structured_claims", status_payload["artifacts"])
                self.assertIn("source_pdf", status_payload)
                self.assertEqual(status_payload["note_count"], 0)

                _, _, add_note_body = dispatch_post_request(
                    f"/api/papers/{paper_id}/notes",
                    json.dumps(
                        {
                            "content": "Compare with the contradicted follow-up paper",
                            "created_by": "agent:http",
                        }
                    ).encode("utf-8"),
                )
                add_note_payload = json.loads(add_note_body.decode("utf-8"))
                self.assertEqual(add_note_payload["created_by"], "agent:http")

                _, _, paper_body = dispatch_get_request(f"/api/papers/{paper_id}")
                paper_payload = json.loads(paper_body.decode("utf-8"))
                self.assertEqual(len(paper_payload["notes"]), 1)

                _, _, notes_body = dispatch_get_request(f"/api/papers/{paper_id}/notes")
                notes_payload = json.loads(notes_body.decode("utf-8"))
                self.assertEqual(notes_payload[0]["content"], "Compare with the contradicted follow-up paper")

                _, _, reviewed_status_body = dispatch_get_request(f"/api/status/{paper_id}")
                reviewed_status_payload = json.loads(reviewed_status_body.decode("utf-8"))
                self.assertEqual(reviewed_status_payload["note_count"], 1)

                claims_payload = json.loads(run_cli("claims", paper_id, cwd=tmp_path).stdout)
                claim_id = claims_payload[0]["id"]
                related_claim_payload = json.loads(run_cli("claims", related_paper_id, cwd=tmp_path).stdout)
                related_claim_id = related_claim_payload[0]["id"]
                _, _, relations_body = dispatch_get_request(f"/api/claims/{claim_id}/relations")
                relations_payload = json.loads(relations_body.decode("utf-8"))
                self.assertIn("inferred_relations", relations_payload)
                self.assertIn("reviewed_relations", relations_payload)
                self.assertEqual(relations_payload["reviewed_relations"], [])

                _, _, promote_body = dispatch_post_request(
                    "/api/review/claim-relations/promote",
                    json.dumps(
                        {
                            "source_claim_id": claim_id,
                            "relation_type": "contradicts",
                            "target_claim_id": related_claim_id,
                            "reviewed_by": "agent:http",
                            "note": "confirmed from service test",
                        }
                    ).encode("utf-8"),
                )
                promote_payload = json.loads(promote_body.decode("utf-8"))
                self.assertEqual(promote_payload["created_by"], "agent:http")

                _, _, reviewed_relations_body = dispatch_get_request(f"/api/claims/{claim_id}/relations")
                reviewed_relations_payload = json.loads(reviewed_relations_body.decode("utf-8"))
                self.assertEqual(len(reviewed_relations_payload["reviewed_relations"]), 1)

                _, _, retract_body = dispatch_post_request(
                    "/api/review/claim-relations/retract",
                    json.dumps(
                        {
                            "source_claim_id": claim_id,
                            "relation_type": "contradicts",
                            "target_claim_id": related_claim_id,
                        }
                    ).encode("utf-8"),
                )
                self.assertTrue(json.loads(retract_body.decode("utf-8"))["deleted"])

                _, _, ui_body = dispatch_get_request("/")
                self.assertIn("RKS Workspace", ui_body.decode("utf-8"))
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
