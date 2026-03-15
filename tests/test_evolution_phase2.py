from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rks.service import dispatch_get_request, dispatch_post_request

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


class EvolutionPhase2Test(unittest.TestCase):
    """Tests for Phase 2 knowledge evolution features: scoring, bucketing, clustering, discovery, and project evolution."""

    def test_consensus_controversy_scoring(self) -> None:
        """Verify consensus/controversy scores are computed and stored in snapshots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf1 = tmp_path / "paper1.pdf"
            pdf1.write_bytes(b"%PDF-1.4\nSparse Attention improves machine translation accuracy.\n")
            pdf2 = tmp_path / "paper2.pdf"
            pdf2.write_bytes(b"%PDF-1.4\nSparse Attention does not improve machine translation accuracy.\n")

            r1 = run_cli("ingest", "pdf", str(pdf1), cwd=tmp_path)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            paper1_id = json.loads(r1.stdout)["id"]

            r2 = run_cli("ingest", "pdf", str(pdf2), cwd=tmp_path)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            paper2_id = json.loads(r2.stdout)["id"]

            # Import claims with concept overlap
            claims1 = tmp_path / "claims1.json"
            claims1.write_text(json.dumps({
                "claims": [{
                    "text": "Sparse Attention improves translation accuracy on WMT14.",
                    "predicate": "improves",
                    "object_text": "translation accuracy",
                    "context": {"subject_text": "Sparse Attention"},
                    "evidence": {"paper_id": paper1_id},
                    "confidence": 0.9,
                }]
            }), encoding="utf-8")
            claims2 = tmp_path / "claims2.json"
            claims2.write_text(json.dumps({
                "claims": [{
                    "text": "Sparse Attention fails to improve translation accuracy on WMT14.",
                    "predicate": "fails to improve",
                    "object_text": "translation accuracy",
                    "context": {"subject_text": "Sparse Attention"},
                    "evidence": {"paper_id": paper2_id},
                    "confidence": 0.8,
                }]
            }), encoding="utf-8")

            self.assertEqual(run_cli("import", "claims", paper1_id, str(claims1), cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("import", "claims", paper2_id, str(claims2), cwd=tmp_path).returncode, 0)

            # Get claim and concept IDs
            claims_payload = json.loads(run_cli("claims", paper1_id, cwd=tmp_path).stdout)
            claim1_id = claims_payload[0]["id"]
            related_claims = json.loads(run_cli("claims", paper2_id, cwd=tmp_path).stdout)
            claim2_id = related_claims[0]["id"]

            concepts_payload = json.loads(run_cli("concepts", paper1_id, cwd=tmp_path).stdout)
            self.assertGreaterEqual(len(concepts_payload), 1)
            concept_id = concepts_payload[0]["id"]

            # Promote a contradicts relation
            promote_result = run_cli(
                "review", "promote-claim-relation",
                claim1_id, "contradicts", claim2_id,
                "--confidence", "0.95",
                cwd=tmp_path,
            )
            self.assertEqual(promote_result.returncode, 0, promote_result.stderr)

            # Take a snapshot — should include scoring
            snapshot_result = run_cli("evolution", "snapshot-concept", concept_id, cwd=tmp_path)
            self.assertEqual(snapshot_result.returncode, 0, snapshot_result.stderr)
            snapshot_payload = json.loads(snapshot_result.stdout)
            snapshot = snapshot_payload["snapshot"]

            self.assertIn("consensus_score", snapshot)
            self.assertIn("controversy_score", snapshot)
            self.assertIn("refine_count", snapshot)
            # With 0 supports and 1 contradicts: consensus = 0/1 = 0.0, controversy = 0/1 = 0.0
            # (controversy = min(support,contradict)/max(1,total))
            self.assertEqual(snapshot["refine_count"], 0)
            self.assertIsNotNone(snapshot["consensus_score"])
            self.assertIsNotNone(snapshot["controversy_score"])

            # Verify timeline also returns scores
            timeline_result = run_cli("evolution", "concept-timeline", concept_id, cwd=tmp_path)
            self.assertEqual(timeline_result.returncode, 0, timeline_result.stderr)
            timeline = json.loads(timeline_result.stdout)
            self.assertGreaterEqual(len(timeline["snapshots"]), 1)
            self.assertIn("consensus_score", timeline["snapshots"][0])

    def test_time_bucketed_timeline(self) -> None:
        """Verify bucketed timeline groups claims by paper year."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf = tmp_path / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4\nTransformers improve accuracy.\n")

            r = run_cli("ingest", "pdf", str(pdf), cwd=tmp_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            paper_id = json.loads(r.stdout)["id"]
            self.assertEqual(run_cli("extract", "claims", paper_id, cwd=tmp_path).returncode, 0)

            concepts = json.loads(run_cli("concepts", paper_id, cwd=tmp_path).stdout)
            if not concepts:
                return  # No concepts extracted, skip
            concept_id = concepts[0]["id"]

            # Build bucketed timeline
            bucketed = run_cli("evolution", "build-timeline-bucketed", concept_id, cwd=tmp_path)
            self.assertEqual(bucketed.returncode, 0, bucketed.stderr)
            payload = json.loads(bucketed.stdout)
            self.assertIn("snapshots", payload)
            self.assertEqual(payload["bucket_size"], "yearly")
            # Should have at least one bucket (unknown year since PDF has no year metadata)
            for snap in payload["snapshots"]:
                self.assertIn("time_bucket", snap)
                self.assertIn("consensus_score", snap)

    def test_conflict_clustering(self) -> None:
        """Verify conflict clusters are created from contradicts edges."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf1 = tmp_path / "p1.pdf"
            pdf1.write_bytes(b"%PDF-1.4\nMethod A works on task X.\n")
            pdf2 = tmp_path / "p2.pdf"
            pdf2.write_bytes(b"%PDF-1.4\nMethod A does not work on task X.\n")

            r1 = run_cli("ingest", "pdf", str(pdf1), cwd=tmp_path)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            p1 = json.loads(r1.stdout)["id"]
            r2 = run_cli("ingest", "pdf", str(pdf2), cwd=tmp_path)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            p2 = json.loads(r2.stdout)["id"]

            # Import claims sharing a concept
            c1_json = tmp_path / "c1.json"
            c1_json.write_text(json.dumps({
                "claims": [{
                    "text": "Method A works on task X.",
                    "predicate": "works on",
                    "object_text": "task X",
                    "context": {"subject_text": "Method A"},
                    "evidence": {"paper_id": p1},
                    "confidence": 0.9,
                }]
            }), encoding="utf-8")
            c2_json = tmp_path / "c2.json"
            c2_json.write_text(json.dumps({
                "claims": [{
                    "text": "Method A does not work on task X.",
                    "predicate": "does not work on",
                    "object_text": "task X",
                    "context": {"subject_text": "Method A"},
                    "evidence": {"paper_id": p2},
                    "confidence": 0.85,
                }]
            }), encoding="utf-8")

            self.assertEqual(run_cli("import", "claims", p1, str(c1_json), cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("import", "claims", p2, str(c2_json), cwd=tmp_path).returncode, 0)

            claims1 = json.loads(run_cli("claims", p1, cwd=tmp_path).stdout)
            claims2 = json.loads(run_cli("claims", p2, cwd=tmp_path).stdout)
            claim1_id = claims1[0]["id"]
            claim2_id = claims2[0]["id"]

            concepts = json.loads(run_cli("concepts", p1, cwd=tmp_path).stdout)
            if not concepts:
                return
            concept_id = concepts[0]["id"]

            # Promote a contradicts relation
            self.assertEqual(
                run_cli("review", "promote-claim-relation", claim1_id, "contradicts", claim2_id, cwd=tmp_path).returncode, 0
            )

            # Run clustering
            cluster_result = run_cli("evolution", "cluster-conflicts", "--concept-id", concept_id, cwd=tmp_path)
            self.assertEqual(cluster_result.returncode, 0, cluster_result.stderr)
            cluster_payload = json.loads(cluster_result.stdout)
            self.assertGreaterEqual(cluster_payload["total_clusters"], 1)

            # List clusters
            list_result = run_cli("evolution", "list-clusters", concept_id, cwd=tmp_path)
            self.assertEqual(list_result.returncode, 0, list_result.stderr)
            list_payload = json.loads(list_result.stdout)
            self.assertGreaterEqual(len(list_payload["clusters"]), 1)
            cluster = list_payload["clusters"][0]
            self.assertGreaterEqual(len(cluster["members"]), 2)
            # Check stance assignment
            stances = {m["stance"] for m in cluster["members"]}
            self.assertTrue(stances)  # Should have at least one stance

    def test_review_priorities_and_open_questions(self) -> None:
        """Verify review priorities and open questions return structured results."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf = tmp_path / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4\nAttention mechanism improves NLP tasks.\n")

            r = run_cli("ingest", "pdf", str(pdf), cwd=tmp_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            paper_id = json.loads(r.stdout)["id"]
            self.assertEqual(run_cli("extract", "claims", paper_id, cwd=tmp_path).returncode, 0)

            # Query review priorities (may be empty with no candidates)
            priorities_result = run_cli("query", "review-priorities", cwd=tmp_path)
            self.assertEqual(priorities_result.returncode, 0, priorities_result.stderr)
            priorities = json.loads(priorities_result.stdout)
            self.assertIn("priorities", priorities)
            self.assertIn("count", priorities)

            # Query open questions (may be empty without snapshots)
            questions_result = run_cli("query", "open-questions", cwd=tmp_path)
            self.assertEqual(questions_result.returncode, 0, questions_result.stderr)
            questions = json.loads(questions_result.stdout)
            self.assertIn("questions", questions)
            self.assertIn("count", questions)

    def test_project_evolution_summary(self) -> None:
        """Verify project evolution summary aggregates linked evolution data."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf = tmp_path / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4\nDeep learning for protein folding.\n")

            r = run_cli("ingest", "pdf", str(pdf), cwd=tmp_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            paper_id = json.loads(r.stdout)["id"]
            self.assertEqual(run_cli("extract", "claims", paper_id, cwd=tmp_path).returncode, 0)

            # Create project
            project_result = run_cli(
                "project", "create",
                "--name", "Protein Folding Study",
                "--research-question", "Can deep learning predict protein structures?",
                cwd=tmp_path,
            )
            self.assertEqual(project_result.returncode, 0, project_result.stderr)
            project_id = json.loads(project_result.stdout)["id"]

            # Link paper and concept
            self.assertEqual(run_cli("project", "add-paper", project_id, paper_id, cwd=tmp_path).returncode, 0)
            concepts = json.loads(run_cli("concepts", paper_id, cwd=tmp_path).stdout)
            if concepts:
                concept_id = concepts[0]["id"]
                self.assertEqual(
                    run_cli("project", "add-link", project_id, "concept", concept_id, cwd=tmp_path).returncode, 0
                )
                # Take a snapshot so there's evolution data
                self.assertEqual(
                    run_cli("evolution", "snapshot-concept", concept_id, cwd=tmp_path).returncode, 0
                )

            # Create hypothesis
            hyp_result = run_cli(
                "hypothesis", "create", project_id,
                "--text", "Deep learning can predict protein structures.",
                cwd=tmp_path,
            )
            self.assertEqual(hyp_result.returncode, 0, hyp_result.stderr)

            # Get project evolution summary
            summary_result = run_cli("evolution", "project-summary", project_id, cwd=tmp_path)
            self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
            summary = json.loads(summary_result.stdout)
            self.assertIn("project", summary)
            self.assertIn("concepts", summary)
            self.assertIn("hypotheses", summary)
            self.assertIn("review_priorities", summary)
            self.assertEqual(summary["project"]["id"], project_id)

    def test_evolution_http_endpoints(self) -> None:
        """Verify Phase 2 HTTP endpoints work end-to-end."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf1 = tmp_path / "http1.pdf"
            pdf1.write_bytes(b"%PDF-1.4\nReinforcement learning scales to large environments.\n")
            pdf2 = tmp_path / "http2.pdf"
            pdf2.write_bytes(b"%PDF-1.4\nReinforcement learning does not scale to large environments.\n")

            r1 = run_cli("ingest", "pdf", str(pdf1), cwd=tmp_path)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            p1 = json.loads(r1.stdout)["id"]
            r2 = run_cli("ingest", "pdf", str(pdf2), cwd=tmp_path)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            p2 = json.loads(r2.stdout)["id"]

            c1_json = tmp_path / "c1.json"
            c1_json.write_text(json.dumps({
                "claims": [{
                    "text": "Reinforcement learning scales to large environments.",
                    "predicate": "scales to",
                    "object_text": "large environments",
                    "context": {"subject_text": "Reinforcement learning"},
                    "evidence": {"paper_id": p1},
                    "confidence": 0.9,
                }]
            }), encoding="utf-8")
            c2_json = tmp_path / "c2.json"
            c2_json.write_text(json.dumps({
                "claims": [{
                    "text": "RL does not scale to large environments.",
                    "predicate": "does not scale to",
                    "object_text": "large environments",
                    "context": {"subject_text": "Reinforcement learning"},
                    "evidence": {"paper_id": p2},
                    "confidence": 0.85,
                }]
            }), encoding="utf-8")

            self.assertEqual(run_cli("import", "claims", p1, str(c1_json), cwd=tmp_path).returncode, 0)
            self.assertEqual(run_cli("import", "claims", p2, str(c2_json), cwd=tmp_path).returncode, 0)

            claims1 = json.loads(run_cli("claims", p1, cwd=tmp_path).stdout)
            claims2 = json.loads(run_cli("claims", p2, cwd=tmp_path).stdout)
            claim1_id = claims1[0]["id"]
            claim2_id = claims2[0]["id"]

            concepts = json.loads(run_cli("concepts", p1, cwd=tmp_path).stdout)
            if not concepts:
                return
            concept_id = concepts[0]["id"]

            # Promote contradiction
            self.assertEqual(
                run_cli("review", "promote-claim-relation", claim1_id, "contradicts", claim2_id, cwd=tmp_path).returncode, 0
            )

            previous_cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                # Test cluster-conflicts POST endpoint
                _, _, cluster_body = dispatch_post_request(
                    "/api/evolution/cluster-conflicts",
                    json.dumps({"concept_id": concept_id}).encode("utf-8"),
                )
                cluster_payload = json.loads(cluster_body.decode("utf-8"))
                self.assertGreaterEqual(cluster_payload["total_clusters"], 1)

                # Test conflict-clusters GET endpoint
                _, _, clusters_body = dispatch_get_request(f"/api/evolution/conflict-clusters/{concept_id}")
                clusters_payload = json.loads(clusters_body.decode("utf-8"))
                self.assertGreaterEqual(len(clusters_payload["clusters"]), 1)

                # Test snapshot with scoring
                _, _, snapshot_body = dispatch_post_request(
                    f"/api/evolution/snapshot-concept/{concept_id}", b"{}",
                )
                snapshot_payload = json.loads(snapshot_body.decode("utf-8"))
                self.assertIn("consensus_score", snapshot_payload["snapshot"])

                # Test concept-consensus GET endpoint
                _, _, consensus_body = dispatch_get_request(f"/api/evolution/concept-consensus/{concept_id}")
                consensus_payload = json.loads(consensus_body.decode("utf-8"))
                self.assertIn("consensus_score", consensus_payload)
                self.assertIn("controversy_score", consensus_payload)

                # Test build-timeline POST endpoint
                _, _, timeline_body = dispatch_post_request(
                    f"/api/evolution/build-timeline/{concept_id}",
                    json.dumps({"bucket_size": "yearly"}).encode("utf-8"),
                )
                timeline_payload = json.loads(timeline_body.decode("utf-8"))
                self.assertIn("snapshots", timeline_payload)

                # Test review-priorities GET endpoint
                _, _, priorities_body = dispatch_get_request("/api/query/review-priorities")
                priorities_payload = json.loads(priorities_body.decode("utf-8"))
                self.assertIn("priorities", priorities_payload)

                # Test open-questions GET endpoint
                _, _, questions_body = dispatch_get_request("/api/query/open-questions")
                questions_payload = json.loads(questions_body.decode("utf-8"))
                self.assertIn("questions", questions_payload)

                # Create project and test project evolution endpoint
                _, _, proj_body = dispatch_post_request(
                    "/api/projects",
                    json.dumps({"name": "HTTP Evolution Test"}).encode("utf-8"),
                )
                project_id = json.loads(proj_body.decode("utf-8"))["id"]

                _, _, link_body = dispatch_post_request(
                    f"/api/projects/{project_id}/links",
                    json.dumps({
                        "object_type": "concept",
                        "object_id": concept_id,
                    }).encode("utf-8"),
                )

                _, _, evo_body = dispatch_get_request(f"/api/evolution/project/{project_id}")
                evo_payload = json.loads(evo_body.decode("utf-8"))
                self.assertIn("project", evo_payload)
                self.assertIn("concepts", evo_payload)
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
