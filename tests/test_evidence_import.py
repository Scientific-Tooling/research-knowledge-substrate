from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from rks.operations.evidence_contract import digest
from rks.operations.evidence_import import import_evidence
from rks.storage.db import (
    _packaged_migration_files,
    connect_db,
    connect_db_readonly,
    initialize_db,
)
from rks.storage.evidence_repository import EvidenceRepository
from rks.storage.paper_repository import PaperRepository
from rks.storage.snapshot import export_graph_snapshot, import_graph_snapshot

from tests._run_cli import run_cli

TIME = "2026-10-26T12:00:00+00:00"


def seal(bundle):
    for item in bundle["items"]:
        basis = {"source_id": bundle["source"]["source_id"], "paper_ref": bundle["source"]["paper_ref"],
                 **{key: item[key] for key in ("kind", "id", "content", "passages")}}
        item["content_revision"] = digest(basis)
        item["revision"] = digest({key: value for key, value in item.items() if key != "revision"})
    return bundle


class EvidenceImportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "source.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nsynthetic source\n%%EOF")
        self.db = self.root / "rks.sqlite3"
        with closing(connect_db(self.db)) as conn:
            initialize_db(conn)
            self.paper = PaperRepository(conn).create_paper_from_pdf(self.pdf, self.pdf)
        self.snapshot = self.root / "snapshot.pdf"
        self.snapshot.write_bytes(self.pdf.read_bytes())
        sha = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.bundle = seal({
            "schema": "scientific-tooling.selected-evidence.v1", "workspace_id": "lab", "paper_id": self.paper.id,
            "source": {"system": "apw", "source_id": "reader", "session_id": "ps_1",
                       "paper_ref": f"rks:lab:{self.paper.id}:sha256:{sha}"},
            "document": {"path": str(self.snapshot), "sha256": sha, "size_bytes": self.snapshot.stat().st_size},
            "exported_at": TIME,
            "items": [{"kind": "annotation", "id": "ann_1", "content": {
                "id": "ann_1", "page": 1, "type": "highlight", "quote": "synthetic source", "anchor": None,
                "rects": [], "comment": "machine interpretation", "tags": [], "createdAt": TIME, "updatedAt": TIME,
            }, "passages": [{"annotation_id": "ann_1", "page": 1, "quote": "synthetic source",
                             "anchor": None, "rects": []}],
                "review": {"status": "unreviewed"},
                "provenance": {"session_id": "ps_1", "created_at": TIME, "updated_at": TIME},
            }],
        })

    def run_import(self, bundle=None, **kwargs):
        with closing(connect_db(self.db) if kwargs.get("apply") else connect_db_readonly(self.db)) as conn:
            return import_evidence(conn, bundle or self.bundle, workspace_id="lab", **kwargs)

    def state(self):
        with closing(connect_db_readonly(self.db)) as conn:
            return list(conn.iterdump())

    def apply(self, bundle=None, **kwargs):
        return self.run_import(bundle, plan=self.run_import(bundle), apply=True, **kwargs)

    def edited(self, comment="edited"):
        bundle = copy.deepcopy(self.bundle)
        bundle["items"][0]["content"]["comment"] = comment
        return seal(bundle)

    def test_dry_run_replay_and_provenance(self):
        before = self.state()
        plan = self.run_import()
        self.assertEqual(plan["counts"], {"addition": 1, "unchanged": 0, "conflict": 0})
        self.assertEqual(before, self.state())
        applied = self.run_import(plan=plan, apply=True)
        self.assertTrue(applied["applied"])
        saved = self.state()
        repeated = self.run_import(plan=plan, apply=True)
        self.assertEqual(repeated["counts"]["unchanged"], 1)
        self.assertEqual(saved, self.state())
        with closing(connect_db_readonly(self.db)) as conn:
            note = conn.execute("SELECT * FROM notes").fetchone()
            self.assertIn("UNREVIEWED", note["content"])
            self.assertEqual(note["created_by"], "external:apw")
            records = EvidenceRepository(conn).list_for_paper(self.paper.id)
            self.assertEqual(records[0]["record"]["item"], self.bundle["items"][0])
            self.assertEqual(len(records[0]["history"]), 1)

    def test_edits_need_explicit_acceptance_and_keep_history(self):
        self.apply()
        edited = self.edited()
        plan = self.run_import(edited)
        before = self.state()
        self.assertEqual(plan["items"][0]["reason"], "revision_changed")
        self.assertFalse(self.run_import(edited, plan=plan, apply=True)["applied"])
        self.assertEqual(before, self.state())
        result = self.run_import(edited, plan=plan, apply=True, accept_updates=True)
        self.assertEqual(result["counts"]["updated"], 1)
        with closing(connect_db_readonly(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 1)
            self.assertEqual(len(EvidenceRepository(conn).list_for_paper(self.paper.id)[0]["history"]), 2)

    def test_conflict_blocks_entire_batch_and_stale_plan_cannot_overwrite(self):
        self.apply()
        first, second = self.edited("first"), self.edited("second")
        plan = self.run_import(first)
        self.apply(second, accept_updates=True)
        before = self.state()
        result = self.run_import(first, plan=plan, apply=True, accept_updates=True)
        self.assertEqual(result["items"][0]["reason"], "plan_stale")
        self.assertEqual(before, self.state())
        extra = copy.deepcopy(first["items"][0])
        extra["id"] = extra["content"]["id"] = extra["passages"][0]["annotation_id"] = "ann_2"
        first["items"].append(extra)
        seal(first)
        self.assertFalse(self.apply(first)["applied"])
        self.assertEqual(before, self.state())

    def test_rollback_after_partial_batch_and_retry(self):
        extra = copy.deepcopy(self.bundle["items"][0])
        extra["id"] = extra["content"]["id"] = extra["passages"][0]["annotation_id"] = "ann_2"
        self.bundle["items"].append(extra)
        seal(self.bundle)
        plan, before = self.run_import(), self.state()
        save = EvidenceRepository.save
        calls = 0

        def interrupted(repo, **kwargs):
            nonlocal calls
            result = save(repo, **kwargs)
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt("simulated interruption after writing a note and its provenance")
            return result

        with patch.object(EvidenceRepository, "save", interrupted), self.assertRaises(KeyboardInterrupt):
            self.run_import(plan=plan, apply=True)
        self.assertEqual(before, self.state())
        self.assertEqual(self.run_import(plan=plan, apply=True)["counts"]["added"], 2)

    def test_hard_process_exit_rolls_back_uncommitted_import(self):
        bundle_file, plan_file = self.root / "bundle.json", self.root / "plan.json"
        bundle_file.write_text(json.dumps(self.bundle), encoding="utf-8")
        plan_file.write_text(json.dumps(self.run_import()), encoding="utf-8")
        before = self.state()
        code = """
import json, os, sys
from pathlib import Path
from rks.storage.db import connect_db
from rks.storage.evidence_repository import EvidenceRepository
from rks.operations.evidence_import import import_evidence
original = EvidenceRepository.save
def crash(self, **kwargs):
    original(self, **kwargs)
    os._exit(23)
EvidenceRepository.save = crash
import_evidence(connect_db(Path(sys.argv[1])), json.loads(Path(sys.argv[2]).read_text()),
                workspace_id='lab', plan=json.loads(Path(sys.argv[3]).read_text()), apply=True)
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.db), str(bundle_file), str(plan_file)],
                                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                                capture_output=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(before, self.state())
        self.assertTrue(self.apply()["applied"])

    def test_competing_identical_and_different_imports(self):
        for different in (False, True):
            with self.subTest(different=different):
                # Use separate source namespaces for the two scenarios.
                original = copy.deepcopy(self.bundle)
                original["source"]["source_id"] = f"reader-{different}"
                seal(original)
                other = copy.deepcopy(original)
                if different:
                    other["items"][0]["content"]["comment"] = "competing edit"
                    seal(other)
                bundles = [original, other]
                plans = [self.run_import(bundle) for bundle in bundles]
                barrier = threading.Barrier(2)

                def worker(index, barrier=barrier, bundles=bundles, plans=plans):
                    barrier.wait(timeout=5)
                    return self.run_import(bundles[index], plan=plans[index], apply=True)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(worker, range(2)))
                self.assertEqual(sum(r["counts"].get("added", 0) for r in results), 1)
                self.assertEqual(sum(r["counts"].get("conflict", 0) for r in results), int(different))

    def test_changed_pdf_and_missing_snapshot_are_not_silently_retargeted(self):
        self.apply()
        self.pdf.write_bytes(b"new source")
        self.assertEqual(self.run_import()["counts"]["unchanged"], 1)
        self.assertEqual(self.run_import(self.edited())["items"][0]["reason"], "paper_source_changed")
        self.snapshot.write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.run_import()

    def test_local_note_edits_block_replay(self):
        self.apply()
        with closing(connect_db(self.db)) as conn:
            conn.execute("UPDATE notes SET content = 'local edit'")
            conn.commit()
        self.assertEqual(self.run_import()["items"][0]["reason"], "imported_note_locally_edited")

    def test_new_document_revision_has_a_distinct_identity(self):
        self.apply()
        self.pdf.write_bytes(b"%PDF-1.4\nnew document revision\n%%EOF")
        newer = copy.deepcopy(self.bundle)
        newer_snapshot = self.root / "newer.pdf"
        newer_snapshot.write_bytes(self.pdf.read_bytes())
        sha = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        newer["document"] = {"path": str(newer_snapshot), "sha256": sha, "size_bytes": newer_snapshot.stat().st_size}
        newer["source"]["paper_ref"] = f"rks:lab:{self.paper.id}:sha256:{sha}"
        seal(newer)
        self.assertEqual(self.apply(newer)["counts"]["added"], 1)
        self.assertEqual(self.run_import()["counts"]["unchanged"], 1)
        with closing(connect_db_readonly(self.db)) as conn:
            self.assertEqual(len(EvidenceRepository(conn).list_for_paper(self.paper.id)), 2)

    def test_cli_preview_missing_workspace_does_not_create_it(self):
        bundle_file = self.root / "bundle.json"
        bundle_file.write_text(json.dumps(self.bundle), encoding="utf-8")
        missing = self.root / "missing-workspace"
        result = run_cli("note", "import-evidence", str(bundle_file), "--workspace-id", "lab", cwd=missing)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(missing.exists())

    def test_plan_and_workspace_validation(self):
        with self.assertRaisesRegex(ValueError, "dry-run plan"):
            self.run_import(apply=True)
        plan = self.run_import()
        with self.assertRaisesRegex(ValueError, "exact bundle"):
            self.run_import(self.edited(), plan=plan, apply=True)
        self.apply()
        changed = copy.deepcopy(self.bundle)
        changed["workspace_id"] = "another"
        changed["source"]["paper_ref"] = changed["source"]["paper_ref"].replace("rks:lab:", "rks:another:")
        seal(changed)
        with closing(connect_db_readonly(self.db)) as conn, self.assertRaisesRegex(ValueError, "bound"):
            import_evidence(conn, changed, workspace_id="another")

    def test_invalid_contracts_fail_before_writes(self):
        before = self.state()
        for mutation in (
            lambda b: b["items"][0]["content"].update(comment="tampered"),
            lambda b: b["items"].append(copy.deepcopy(b["items"][0])),
            lambda b: b["items"][0].update(review={"status": "reviewed"}),
            lambda b: b["items"][0]["passages"][0].update(page=True),
            lambda b: b["items"][0].update(kind="delete"),
        ):
            bad = copy.deepcopy(self.bundle)
            mutation(bad)
            with self.assertRaises(ValueError):
                self.run_import(bad)
        self.assertEqual(before, self.state())

    def test_merge_redirect_and_backup_roundtrip_preserve_identity(self):
        self.apply()
        with closing(connect_db(self.db)) as conn:
            target = PaperRepository(conn).create_paper_from_pdf(self.pdf, self.pdf, title="canonical")
        result = run_cli("papers", "merge", target.id, self.paper.id, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_import()["items"][0]["paper_id"], target.id)
        self.assertEqual(self.run_import()["counts"]["unchanged"], 1)
        self.assertTrue(self.apply(self.edited(), accept_updates=True)["applied"])
        snapshot = self.root / "graph.json"
        with closing(connect_db_readonly(self.db)) as conn:
            export_graph_snapshot(conn, snapshot)
        restored = self.root / "restored.db"
        with closing(connect_db(restored)) as conn:
            initialize_db(conn)
            import_graph_snapshot(conn, snapshot)
        self.db = restored
        self.assertEqual(self.run_import(self.edited())["counts"]["unchanged"], 1)

    def test_migration_copies_match_and_preview_does_not_migrate(self):
        for packaged in _packaged_migration_files():
            source = Path(__file__).resolve().parents[1] / "migrations" / packaged.name
            self.assertEqual(source.read_text(encoding="utf-8"), packaged.read_text(encoding="utf-8"))
        with closing(connect_db(self.db)) as conn:
            conn.execute("DROP TABLE external_evidence")
            conn.commit()
        before = self.state()
        with self.assertRaisesRegex(ValueError, "rks migrate"):
            self.run_import()
        self.assertEqual(before, self.state())
