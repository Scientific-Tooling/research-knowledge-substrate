from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rks import __version__
from rks.agent_skills import SKILL_BUNDLE_VERSION
from rks.cli.main import build_parser


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
    def test_parser_supports_pmid_and_url_ingest(self) -> None:
        parser = build_parser()

        pmid_args = parser.parse_args(["ingest", "pmid", "31452104"])
        self.assertEqual(pmid_args.ingest_command, "pmid")
        self.assertEqual(pmid_args.pmid, "31452104")

        url_args = parser.parse_args(["ingest", "url", "https://pubmed.ncbi.nlm.nih.gov/31452104/"])
        self.assertEqual(url_args.ingest_command, "url")
        self.assertEqual(url_args.url, "https://pubmed.ncbi.nlm.nih.gov/31452104/")

        eval_args = parser.parse_args(["evaluate", "baseline", "baseline.json"])
        self.assertEqual(eval_args.evaluate_command, "baseline")
        self.assertEqual(str(eval_args.spec_path), "baseline.json")

        mcp_args = parser.parse_args(["mcp"])
        self.assertEqual(mcp_args.command, "mcp")

    def test_skills_list_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            list_result = run_cli("skills", "list", cwd=tmp_path)
            self.assertEqual(list_result.returncode, 0, list_result.stderr)
            list_payload = json.loads(list_result.stdout)
            skill_names = [entry["name"] for entry in list_payload]
            self.assertIn("rks-codex-operator", skill_names)
            self.assertIn("rks-query-substrate", skill_names)
            self.assertIn("rks-paper-discussion", skill_names)

            export_dir = tmp_path / "rks-agent-kit"
            export_result = run_cli("skills", "export", str(export_dir), cwd=tmp_path)
            self.assertEqual(export_result.returncode, 0, export_result.stderr)
            export_payload = json.loads(export_result.stdout)
            self.assertEqual(export_payload["bundle_version"], SKILL_BUNDLE_VERSION)
            self.assertEqual(export_payload["skill_count"], len(list_payload))
            self.assertTrue((export_dir / "skills-index.json").exists())
            self.assertTrue((export_dir / "bundle-metadata.json").exists())
            self.assertTrue((export_dir / "AGENTS.md").exists())
            self.assertTrue((export_dir / "CLAUDE.md").exists())
            self.assertTrue((export_dir / "README.md").exists())
            self.assertTrue((export_dir / "skills" / "rks-codex-operator" / "SKILL.md").exists())
            self.assertTrue((export_dir / "skills" / "rks-paper-discussion" / "SKILL.md").exists())
            bundle_metadata = json.loads((export_dir / "bundle-metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle_metadata["bundle_version"], SKILL_BUNDLE_VERSION)
            self.assertEqual(bundle_metadata["skill_count"], len(list_payload))

    def test_doctor_reports_installation_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            before_result = run_cli("doctor", cwd=tmp_path)
            self.assertEqual(before_result.returncode, 0, before_result.stderr)
            before_payload = json.loads(before_result.stdout)
            self.assertEqual(before_payload["version"], __version__)
            self.assertEqual(before_payload["overall_status"], "action_required")
            self.assertIn("rks config init", before_payload["recommended_actions"])
            self.assertIn("rks init-db", before_payload["recommended_actions"])

            self.assertEqual(run_cli("config", "init", cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("init-db", cwd=tmp_path).returncode, 0)

            after_result = run_cli("doctor", cwd=tmp_path)
            self.assertEqual(after_result.returncode, 0, after_result.stderr)
            after_payload = json.loads(after_result.stdout)
            self.assertEqual(after_payload["overall_status"], "ok")
            self.assertEqual(after_payload["checks"]["bundled_skills"]["bundle_version"], SKILL_BUNDLE_VERSION)

    def test_init_db_and_ingest_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "example-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Transformers improve translation accuracy on WMT14.\n"
                b"Diffusion models reduce image artifacts in generation.\n"
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
            self.assertIn("sections", artifact_types)
            self.assertEqual(show_payload["notes"], [])

            note_result = run_cli(
                "note",
                "add",
                "paper",
                payload["id"],
                "--content",
                "Focus on benchmark setup",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(note_result.returncode, 0, note_result.stderr)
            note_payload = json.loads(note_result.stdout)
            self.assertEqual(note_payload["target_id"], payload["id"])
            self.assertEqual(note_payload["created_by"], "human:test")

            notes_result = run_cli("note", "list", "paper", payload["id"], cwd=tmp_path)
            self.assertEqual(notes_result.returncode, 0, notes_result.stderr)
            notes_payload = json.loads(notes_result.stdout)
            self.assertEqual(len(notes_payload), 1)
            self.assertEqual(notes_payload[0]["content"], "Focus on benchmark setup")

            project_create_result = run_cli(
                "project",
                "create",
                "--name",
                "Sparse Attention Review",
                "--description",
                "Track the strongest long-context evidence.",
                "--research-question",
                "Which sparse attention papers matter most for long-context evaluation?",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(project_create_result.returncode, 0, project_create_result.stderr)
            project_payload = json.loads(project_create_result.stdout)
            self.assertEqual(project_payload["id"], "rp_000001")
            self.assertEqual(project_payload["created_by"], "human:test")

            project_list_result = run_cli("project", "list", cwd=tmp_path)
            self.assertEqual(project_list_result.returncode, 0, project_list_result.stderr)
            project_list_payload = json.loads(project_list_result.stdout)
            self.assertEqual(len(project_list_payload), 1)
            self.assertEqual(project_list_payload[0]["name"], "Sparse Attention Review")

            project_note_result = run_cli(
                "note",
                "add",
                "project",
                project_payload["id"],
                "--content",
                "Keep a separate view of benchmark realism.",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(project_note_result.returncode, 0, project_note_result.stderr)
            self.assertEqual(json.loads(project_note_result.stdout)["target_type"], "project")

            project_link_result = run_cli(
                "project",
                "add-paper",
                project_payload["id"],
                payload["id"],
                "--link-type",
                "key_evidence",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(project_link_result.returncode, 0, project_link_result.stderr)
            project_link_payload = json.loads(project_link_result.stdout)
            self.assertEqual(project_link_payload["link"]["link_type"], "key_evidence")
            self.assertEqual(project_link_payload["paper"]["id"], payload["id"])

            duplicate_project_link_result = run_cli(
                "project",
                "add-paper",
                project_payload["id"],
                payload["id"],
                "--link-type",
                "key_evidence",
                cwd=tmp_path,
            )
            self.assertEqual(duplicate_project_link_result.returncode, 0, duplicate_project_link_result.stderr)
            duplicate_project_link_payload = json.loads(duplicate_project_link_result.stdout)
            self.assertEqual(duplicate_project_link_payload["link"]["id"], project_link_payload["link"]["id"])

            project_notes_result = run_cli("note", "list", "project", project_payload["id"], cwd=tmp_path)
            self.assertEqual(project_notes_result.returncode, 0, project_notes_result.stderr)
            project_notes_payload = json.loads(project_notes_result.stdout)
            self.assertEqual(len(project_notes_payload), 1)
            self.assertEqual(project_notes_payload[0]["content"], "Keep a separate view of benchmark realism.")

            project_papers_result = run_cli("project", "papers", project_payload["id"], cwd=tmp_path)
            self.assertEqual(project_papers_result.returncode, 0, project_papers_result.stderr)
            project_papers_payload = json.loads(project_papers_result.stdout)
            self.assertEqual(len(project_papers_payload), 1)
            self.assertEqual(project_papers_payload[0]["paper"]["id"], payload["id"])

            show_project_result = run_cli("show", "project", project_payload["id"], cwd=tmp_path)
            self.assertEqual(show_project_result.returncode, 0, show_project_result.stderr)
            show_project_payload = json.loads(show_project_result.stdout)
            self.assertEqual(show_project_payload["id"], project_payload["id"])
            self.assertEqual(len(show_project_payload["notes"]), 1)
            self.assertEqual(len(show_project_payload["papers"]), 1)

            extract_claims_result = run_cli("extract", "claims", payload["id"], cwd=tmp_path)
            self.assertEqual(extract_claims_result.returncode, 0, extract_claims_result.stderr)
            extract_claims_payload = json.loads(extract_claims_result.stdout)
            self.assertGreaterEqual(extract_claims_payload["claim_count"], 1)

            rerun_claims_result = run_cli("extract", "claims", payload["id"], cwd=tmp_path)
            self.assertEqual(rerun_claims_result.returncode, 0, rerun_claims_result.stderr)

            claims_result = run_cli("claims", payload["id"], cwd=tmp_path)
            self.assertEqual(claims_result.returncode, 0, claims_result.stderr)
            claims_payload = json.loads(claims_result.stdout)
            self.assertEqual(len(claims_payload), 2)
            self.assertEqual(claims_payload[0]["subject"], "Transformer")
            self.assertIn(claims_payload[0]["predicate"], {"supports", "improves"})
            self.assertIn("section", claims_payload[0]["evidence"])

            concepts_result = run_cli("concepts", payload["id"], cwd=tmp_path)
            self.assertEqual(concepts_result.returncode, 0, concepts_result.stderr)
            concepts_payload = json.loads(concepts_result.stdout)
            concept_names = [concept["name"] for concept in concepts_payload]
            self.assertIn("Transformer", concept_names)
            self.assertIn("Diffusion Model", concept_names)

            query_result = run_cli("query", "claims-about", "Transformer", cwd=tmp_path)
            self.assertEqual(query_result.returncode, 0, query_result.stderr)
            query_payload = json.loads(query_result.stdout)
            self.assertEqual(query_payload["concept"]["name"], "Transformer")
            self.assertEqual(len(query_payload["claims"]), 1)

            claim_id = claims_payload[0]["id"]
            supporting_result = run_cli("query", "papers-supporting", claim_id, cwd=tmp_path)
            self.assertEqual(supporting_result.returncode, 0, supporting_result.stderr)
            supporting_payload = json.loads(supporting_result.stdout)
            self.assertEqual(supporting_payload["papers"][0]["id"], payload["id"])

            show_claim_result = run_cli("show", "claim", claim_id, cwd=tmp_path)
            self.assertEqual(show_claim_result.returncode, 0, show_claim_result.stderr)
            show_claim_payload = json.loads(show_claim_result.stdout)
            self.assertEqual(show_claim_payload["subject"], "Transformer")
            self.assertGreaterEqual(len(show_claim_payload["edges"]), 2)
            self.assertIn("section", show_claim_payload["evidence"])

            hypothesis_create_result = run_cli(
                "hypothesis",
                "create",
                project_payload["id"],
                "--text",
                "Sparse attention gains hold only under realistic long-context benchmarks.",
                "--status",
                "active",
                "--confidence",
                "0.7",
                "--context",
                json.dumps({"scope": "long-context evaluation", "owner": "human:test"}),
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(hypothesis_create_result.returncode, 0, hypothesis_create_result.stderr)
            hypothesis_payload = json.loads(hypothesis_create_result.stdout)
            self.assertEqual(hypothesis_payload["id"], "h_000001")
            self.assertEqual(hypothesis_payload["project_id"], project_payload["id"])
            self.assertEqual(hypothesis_payload["status"], "active")

            hypothesis_list_result = run_cli("hypothesis", "list", project_payload["id"], cwd=tmp_path)
            self.assertEqual(hypothesis_list_result.returncode, 0, hypothesis_list_result.stderr)
            hypothesis_list_payload = json.loads(hypothesis_list_result.stdout)
            self.assertEqual(len(hypothesis_list_payload), 1)
            self.assertEqual(hypothesis_list_payload[0]["text"], hypothesis_payload["text"])

            hypothesis_paper_evidence_result = run_cli(
                "hypothesis",
                "add-evidence",
                hypothesis_payload["id"],
                "paper",
                payload["id"],
                "--relation-type",
                "supported_by",
                "--note",
                "Primary benchmark anchor.",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(hypothesis_paper_evidence_result.returncode, 0, hypothesis_paper_evidence_result.stderr)
            hypothesis_paper_evidence_payload = json.loads(hypothesis_paper_evidence_result.stdout)
            self.assertEqual(hypothesis_paper_evidence_payload["paper"]["id"], payload["id"])

            hypothesis_claim_evidence_result = run_cli(
                "hypothesis",
                "add-evidence",
                hypothesis_payload["id"],
                "claim",
                claim_id,
                "--relation-type",
                "refined_by",
                "--created-by",
                "human:test",
                cwd=tmp_path,
            )
            self.assertEqual(hypothesis_claim_evidence_result.returncode, 0, hypothesis_claim_evidence_result.stderr)
            hypothesis_claim_evidence_payload = json.loads(hypothesis_claim_evidence_result.stdout)
            self.assertEqual(hypothesis_claim_evidence_payload["claim"]["id"], claim_id)

            hypothesis_evidence_result = run_cli("hypothesis", "evidence", hypothesis_payload["id"], cwd=tmp_path)
            self.assertEqual(hypothesis_evidence_result.returncode, 0, hypothesis_evidence_result.stderr)
            hypothesis_evidence_payload = json.loads(hypothesis_evidence_result.stdout)
            self.assertEqual(len(hypothesis_evidence_payload), 2)

            show_hypothesis_result = run_cli("show", "hypothesis", hypothesis_payload["id"], cwd=tmp_path)
            self.assertEqual(show_hypothesis_result.returncode, 0, show_hypothesis_result.stderr)
            show_hypothesis_payload = json.loads(show_hypothesis_result.stdout)
            self.assertEqual(show_hypothesis_payload["id"], hypothesis_payload["id"])
            self.assertEqual(show_hypothesis_payload["project"]["id"], project_payload["id"])
            self.assertEqual(len(show_hypothesis_payload["evidence_links"]), 2)

            search_result = run_cli("search", "Transformer", cwd=tmp_path)
            self.assertEqual(search_result.returncode, 0, search_result.stderr)
            search_payload = json.loads(search_result.stdout)
            self.assertGreaterEqual(len(search_payload["claims"]), 1)
            self.assertGreaterEqual(len(search_payload["concepts"]), 1)

            final_show_result = run_cli("show", "paper", payload["id"], cwd=tmp_path)
            self.assertEqual(final_show_result.returncode, 0, final_show_result.stderr)
            final_show_payload = json.loads(final_show_result.stdout)
            final_artifact_types = [artifact["artifact_type"] for artifact in final_show_payload["artifacts"]]
            self.assertEqual(final_artifact_types.count("structured_claims"), 1)
            self.assertEqual(final_artifact_types.count("claim_candidates"), 1)
            self.assertEqual(final_artifact_types.count("normalized_claims"), 1)
            self.assertEqual(len(final_show_payload["notes"]), 1)

            final_project_result = run_cli("show", "project", project_payload["id"], cwd=tmp_path)
            self.assertEqual(final_project_result.returncode, 0, final_project_result.stderr)
            final_project_payload = json.loads(final_project_result.stdout)
            self.assertEqual(len(final_project_payload["hypotheses"]), 1)

    def test_project_links_outputs_and_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            paper_a = tmp_path / "project-a.pdf"
            paper_a.write_bytes(
                b"%PDF-1.4\nWe propose Sparse Attention. Sparse Attention improves translation accuracy on WMT14.\n"
            )
            paper_b = tmp_path / "project-b.pdf"
            paper_b.write_bytes(
                b"%PDF-1.4\nSparse Attention does not improve translation accuracy on WMT14.\n"
            )

            paper_a_id = json.loads(run_cli("ingest", "pdf", str(paper_a), cwd=tmp_path).stdout)["id"]
            paper_b_id = json.loads(run_cli("ingest", "pdf", str(paper_b), cwd=tmp_path).stdout)["id"]

            claims_a_path = tmp_path / "project-a-claims.json"
            claims_a_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Sparse Attention improves translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                                "evidence": {"paper_id": paper_a_id},
                                "confidence": 0.91,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            claims_b_path = tmp_path / "project-b-claims.json"
            claims_b_path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Sparse Attention does not improve translation accuracy on WMT14.",
                                "predicate": "improves",
                                "object_text": "translation accuracy",
                                "context": {"subject_text": "Sparse Attention", "dataset": "WMT14"},
                                "evidence": {"paper_id": paper_b_id},
                                "confidence": 0.74,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(run_cli("import", "claims", paper_a_id, str(claims_a_path), cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("import", "claims", paper_b_id, str(claims_b_path), cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("extract", "methods", paper_a_id, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("extract", "datasets", paper_a_id, cwd=tmp_path).returncode, 0)

            claim_a_id = json.loads(run_cli("claims", paper_a_id, cwd=tmp_path).stdout)[0]["id"]
            claim_b_id = json.loads(run_cli("claims", paper_b_id, cwd=tmp_path).stdout)[0]["id"]
            method_id = json.loads(run_cli("methods", paper_a_id, cwd=tmp_path).stdout)[0]["id"]
            dataset_id = json.loads(run_cli("datasets", paper_a_id, cwd=tmp_path).stdout)[0]["id"]
            concept_id = json.loads(run_cli("concepts", paper_a_id, cwd=tmp_path).stdout)[0]["id"]

            project_id = json.loads(
                run_cli(
                    "project",
                    "create",
                    "--name",
                    "Sparse Attention Project",
                    "--research-question",
                    "Does sparse attention hold up on realistic translation benchmarks?",
                    cwd=tmp_path,
                ).stdout
            )["id"]

            self.assertEqual(run_cli("project", "add-paper", project_id, paper_a_id, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("project", "add-link", project_id, "claim", claim_a_id, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("project", "add-link", project_id, "method", method_id, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("project", "add-link", project_id, "dataset", dataset_id, cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("project", "add-link", project_id, "concept", concept_id, cwd=tmp_path).returncode, 0)
            self.assertEqual(
                run_cli(
                    "review",
                    "promote-claim-relation",
                    claim_a_id,
                    "contradicts",
                    claim_b_id,
                    "--reviewed-by",
                    "agent:test",
                    cwd=tmp_path,
                ).returncode,
                0,
            )

            hypothesis_id = json.loads(
                run_cli(
                    "hypothesis",
                    "create",
                    project_id,
                    "--text",
                    "Sparse attention only survives under selective benchmark conditions.",
                    "--status",
                    "active",
                    cwd=tmp_path,
                ).stdout
            )["id"]
            self.assertEqual(
                run_cli("hypothesis", "add-evidence", hypothesis_id, "claim", claim_a_id, cwd=tmp_path).returncode,
                0,
            )

            links_result = run_cli("project", "links", project_id, cwd=tmp_path)
            self.assertEqual(links_result.returncode, 0, links_result.stderr)
            links_payload = json.loads(links_result.stdout)
            self.assertEqual({entry["link"]["object_type"] for entry in links_payload}, {"paper", "claim", "method", "dataset", "concept"})

            claim_links_result = run_cli("project", "links", project_id, "--object-type", "claim", cwd=tmp_path)
            self.assertEqual(claim_links_result.returncode, 0, claim_links_result.stderr)
            self.assertEqual(len(json.loads(claim_links_result.stdout)), 1)

            show_project_payload = json.loads(run_cli("show", "project", project_id, cwd=tmp_path).stdout)
            self.assertEqual(len(show_project_payload["papers"]), 1)
            self.assertEqual(len(show_project_payload["claims"]), 1)
            self.assertEqual(len(show_project_payload["methods"]), 1)
            self.assertEqual(len(show_project_payload["datasets"]), 1)
            self.assertEqual(len(show_project_payload["concepts"]), 1)

            project_brief_result = run_cli("output", "project-brief", project_id, cwd=tmp_path)
            self.assertEqual(project_brief_result.returncode, 0, project_brief_result.stderr)
            project_brief_payload = json.loads(project_brief_result.stdout)
            self.assertEqual(project_brief_payload["scope_type"], "project")
            self.assertEqual(project_brief_payload["research_question"], "Does sparse attention hold up on realistic translation benchmarks?")
            self.assertEqual(len(project_brief_payload["hypotheses"]), 1)

            project_review_result = run_cli("output", "project-review-priorities", project_id, cwd=tmp_path)
            self.assertEqual(project_review_result.returncode, 0, project_review_result.stderr)
            project_review_payload = json.loads(project_review_result.stdout)
            self.assertEqual(project_review_payload["scope_type"], "project")
            self.assertGreaterEqual(len(project_review_payload["review_priorities"]), 1)

            planner_result = run_cli(
                "plan",
                "query",
                "What should we review next?",
                "--project-id",
                project_id,
                cwd=tmp_path,
            )
            self.assertEqual(planner_result.returncode, 0, planner_result.stderr)
            planner_payload = json.loads(planner_result.stdout)
            self.assertEqual(planner_payload["scope"]["type"], "project")
            self.assertEqual(planner_payload["recommended_surface"], "project_review_priorities")


if __name__ == "__main__":
    unittest.main()
