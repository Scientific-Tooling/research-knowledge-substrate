"""Engineering fixtures only: these reviewer assertions are not scientific reviews."""
from __future__ import annotations

import copy
import json
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

from rks.operations.comparison import apply_comparison, list_comparisons, list_evidence, show_comparison
from rks.storage.comparison_repository import ComparisonRepository
from rks.storage.db import connect_db, connect_db_readonly, initialize_db
from rks.storage.snapshot import export_graph_snapshot, import_graph_snapshot
from tests import test_evidence_import as fixtures
from tests._run_cli import run_cli


class ComparisonTest(unittest.TestCase):
    run_import = fixtures.EvidenceImportTest.run_import
    import_bundle = fixtures.EvidenceImportTest.apply
    state = fixtures.EvidenceImportTest.state
    edited = fixtures.EvidenceImportTest.edited

    def setUp(self):
        fixtures.EvidenceImportTest.setUp(self)
        self.scope = {"workspace_id": "lab", "source_id": "reader",
                      "paper_sources": [f"{self.paper.id}:{self.bundle['document']['sha256']}"]}
        self.import_bundle()
        with closing(connect_db_readonly(self.db)) as conn:
            evidence = list_evidence(conn, **self.scope)["evidence"][0]
        self.selection = {k: evidence[k] for k in ("note_id", "revision")}

    def request(self, action, payload, current=None):
        return {"schema": "rks.comparison-request.v1", "request_id": uuid.uuid4().hex, "action": action,
                "comparison_id": current["id"] if current else None,
                "expected_revision": current["revision"] if current else None, "payload": payload}

    def mutate(self, request, **scope):
        with closing(connect_db(self.db)) as conn:
            return apply_comparison(conn, request, **(scope or self.scope))

    def show(self, current, history=False):
        with closing(connect_db_readonly(self.db)) as conn:
            conn.execute("BEGIN")
            return show_comparison(conn, current["id"], history=history, **self.scope)

    def create(self):
        return self.mutate(self.request("create", {"title": "Methods", "question": "How do assumptions differ?",
                                                  "criteria": ["Metric", "Limitations"]}))["comparison"]

    def set_request(self, current, **changes):
        payload = {"paper_source": self.scope["paper_sources"][0], "criterion_id": "c1",
                   "text": "Did not improve from 0.10 to 0.20 (95% CI).", "conditions": "Dataset A; donor-level; n=12.",
                   "origin": "agent", "evidence": [self.selection], **changes}
        return self.request("set", payload, current)

    def review_request(self, current, **changes):
        return self.request("review", {"paper_source": self.scope["paper_sources"][0], "criterion_id": "c1",
            "reviewer": "Synthetic fixture reviewer", "scope": "Numbers, conditions and negation",
            "decision": "accepted", "statement": "Synthetic test assertion, not an actual scientific review.", **changes}, current)

    def test_gaps_unsupported_entries_and_preserved_literal_conditions(self):
        current = self.create()
        self.assertEqual([c["support_status"] for c in current["cells"]], ["gap", "gap"])
        with self.assertRaisesRegex(ValueError, "gaps remain gaps"):
            self.mutate(self.review_request(current))
        current = self.mutate(self.set_request(current, evidence=[]))["comparison"]
        self.assertEqual(current["cells"][0]["support_status"], "unsupported")
        with self.assertRaises(ValueError):
            self.mutate(self.review_request(current))
        current = self.mutate(self.set_request(current))["comparison"]
        cell = current["cells"][0]
        self.assertEqual(cell["text"], "Did not improve from 0.10 to 0.20 (95% CI).")
        self.assertEqual(cell["conditions"], "Dataset A; donor-level; n=12.")
        self.assertEqual(cell["origin"], "agent")
        self.assertEqual(cell["evidence"][0]["record"]["item"]["passages"][0]["quote"], "synthetic source")
        self.assertEqual(cell["support_status"], "linked")
        self.assertEqual(current["cells"][1]["support_status"], "gap")

    def test_review_replay_history_stale_edits_and_no_review_promotion(self):
        current = self.mutate(self.set_request(self.create()))["comparison"]
        request = self.review_request(current)
        current = self.mutate(request)["comparison"]
        self.assertEqual(current["cells"][0]["review"]["status"], "accepted")
        replay = self.mutate(request)
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(replay["comparison"]["cells"][0]["review"]["history"]), 1)
        self.assertEqual(current["cells"][0]["evidence"][0]["record"]["item"]["review"]["status"], "unreviewed")
        current = self.mutate(self.set_request(current, conditions="Different population; n=24."))["comparison"]
        self.assertEqual(current["cells"][0]["review"]["status"], "stale")
        restored_text = self.mutate(self.set_request(current))["comparison"]
        self.assertEqual(restored_text["cells"][0]["review"]["status"], "stale")
        history = self.show(current, history=True)["history"]
        self.assertEqual(len(history), 4)
        self.assertEqual(history[1]["cells"][0]["conditions"], "Dataset A; donor-level; n=12.")

    def test_changed_evidence_and_missing_pdf_invalidate_reviews_without_erasing_quotes(self):
        current = self.mutate(self.set_request(self.create()))["comparison"]
        current = self.mutate(self.review_request(current))["comparison"]
        self.import_bundle(self.edited(), accept_updates=True)
        stale = self.show(current)["cells"][0]
        self.assertEqual(stale["review"]["status"], "stale")
        self.assertEqual(stale["evidence"][0]["status"], "evidence_changed")
        self.assertEqual(stale["evidence"][0]["record"]["item"]["content"]["comment"], "machine interpretation")
        with self.assertRaisesRegex(ValueError, "Selected evidence changed"):
            self.mutate(self.set_request(self.show(current)))
        self.snapshot.unlink()
        self.assertEqual(self.show(current)["cells"][0]["evidence"][0]["source_status"], "source_unavailable")

    def test_scope_cas_and_failed_transaction_preserve_state(self):
        current = self.create()
        before = self.state()
        with self.assertRaisesRegex(ValueError, "outside"):
            with closing(connect_db_readonly(self.db)) as conn:
                show_comparison(conn, current["id"], **{**self.scope, "source_id": "foreign"})
        with patch.object(ComparisonRepository, "remember", side_effect=RuntimeError("interrupted transaction")):
            with self.assertRaises(RuntimeError):
                self.mutate(self.set_request(current))
        self.assertEqual(before, self.state())
        self.mutate(self.set_request(current))
        with self.assertRaisesRegex(ValueError, "changed after inspection"):
            self.mutate(self.set_request(current, text="Stale writer"))
        wrong = copy.deepcopy(self.scope)
        wrong["paper_sources"] = [f"{self.paper.id}:{'0' * 64}"]
        with closing(connect_db_readonly(self.db)) as conn:
            self.assertEqual(list_comparisons(conn, **wrong)["comparisons"], [])

    def test_competing_reviews_one_wins_and_identical_request_replays(self):
        current = self.mutate(self.set_request(self.create()))["comparison"]
        requests = [self.review_request(current), self.review_request(current, decision="needs_changes")]
        def apply(request):
            try:
                return self.mutate(request)
            except ValueError as exc:
                return str(exc)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(apply, requests))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(len(self.show(current)["cells"][0]["review"]["history"]), 1)
        request = self.set_request(self.show(current), text="New interpretation")
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(self.mutate, [request, request]))
        self.assertEqual(sorted(r["replayed"] for r in results), [False, True])
        bad = copy.deepcopy(request)
        bad["payload"]["text"] = "Changed retry"
        with self.assertRaisesRegex(ValueError, "different comparison content"):
            self.mutate(bad)

    def test_read_only_cli_backup_and_migration_parity(self):
        current = self.mutate(self.set_request(self.create()))["comparison"]
        current = self.mutate(self.review_request(current))["comparison"]
        args = ["comparison", "show", current["id"], "--workspace-id", "lab", "--source-id", "reader",
                "--paper-source", self.scope["paper_sources"][0]]
        before = self.state()
        result = run_cli(*args, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["revision"], current["revision"])
        self.assertEqual(self.state(), before)
        missing = self.root / "missing"
        self.assertEqual(run_cli(*args, cwd=missing).returncode, 1)
        self.assertFalse(missing.exists())
        snapshot = self.root / "snapshot.json"
        with closing(connect_db_readonly(self.db)) as conn:
            export_graph_snapshot(conn, snapshot)
        with closing(connect_db(self.root / "restored.db")) as conn:
            initialize_db(conn)
            import_graph_snapshot(conn, snapshot)
            restored = show_comparison(conn, current["id"], **self.scope)
            self.assertEqual(restored, current)
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / "migrations/0015_comparisons.sql").read_bytes(),
                         (root / "src/rks/migrations/0015_comparisons.sql").read_bytes())
