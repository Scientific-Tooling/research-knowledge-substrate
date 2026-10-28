"""Frozen engineering cases for scoped evidence retrieval, not scientific relevance labels."""
from __future__ import annotations

import copy
import json
import unittest
from contextlib import closing

from rks.operations.evidence_search import search_evidence
from rks.storage.db import connect_db, connect_db_readonly
from rks.storage.paper_repository import PaperRepository
from tests import test_evidence_import as fixtures
from tests._run_cli import run_cli


class EvidenceSearchTest(unittest.TestCase):
    setUp = fixtures.EvidenceImportTest.setUp
    apply = fixtures.EvidenceImportTest.apply
    run_import = fixtures.EvidenceImportTest.run_import
    state = fixtures.EvidenceImportTest.state
    edited = fixtures.EvidenceImportTest.edited

    def search(self, query, **options):
        scope = [f"{self.paper.id}:{self.bundle['document']['sha256']}"]
        with closing(connect_db_readonly(self.db)) as conn:
            conn.execute("BEGIN")
            return search_evidence(conn, query, **{
                "workspace_id": "lab", "source_id": "reader", "paper_sources": scope, **options})

    def test_frozen_query_cases_distinguish_source_commentary_and_metadata(self):
        self.apply()
        before = self.state()
        for query, mode, expected in [
            ("synthetic source", "lexical", ["source"]),
            ("INTERPRETATION", "lexical", ["commentary"]),
            ("synthetic interpretation", "lexical", ["source", "commentary"]),
            ("synthetic interpretation", "phrase", []),
            ("SYNTHETIC SOURCE", "phrase", ["source"]),
            ("unreviewed", "lexical", []), ("ps_1", "phrase", []),
            ("", "lexical", []), ("!!!", "lexical", []), ("unknownword", "lexical", []),
        ]:
            with self.subTest(query=query, mode=mode):
                result = self.search(query, mode=mode)
                self.assertEqual([m["role"] for r in result["results"] for m in r["matches"]], expected)
        self.assertEqual(before, self.state())

    def test_exact_scope_review_filters_and_replay(self):
        self.apply()
        self.apply()
        self.assertEqual(self.search("source")["total"], 1)
        self.assertEqual(self.search("source", source_id="different")["total"], 0)
        self.assertEqual(self.search("source", paper_sources=[f"{self.paper.id}:{'0' * 64}"])["total"], 0)
        self.assertEqual(self.search("source", review="reviewed")["total"], 0)
        with self.assertRaisesRegex(ValueError, "different evidence workspace"):
            self.search("source", workspace_id="other")
        reviewed = copy.deepcopy(self.bundle)
        item = reviewed["items"][0]
        item["review"] = {"status": "reviewed", "method": "human", "reviewer": "Synthetic test reviewer",
                          "statement": "Engineering fixture, not an actual scientific review.",
                          "reviewed_at": fixtures.TIME, "content_revision": item["content_revision"]}
        self.apply(fixtures.seal(reviewed), accept_updates=True)
        self.assertEqual(self.search("source", review="reviewed")["total"], 1)
        self.assertEqual(self.search("source", review="unreviewed")["total"], 0)
        self.apply(self.edited(), accept_updates=True)
        self.assertEqual(self.search("source", review="reviewed")["total"], 0)

    def test_duplicate_text_keeps_distinct_identities_and_stable_pagination(self):
        duplicate = copy.deepcopy(self.bundle["items"][0])
        duplicate["id"] = duplicate["content"]["id"] = duplicate["passages"][0]["annotation_id"] = "ann_2"
        self.bundle["items"].append(duplicate)
        fixtures.seal(self.bundle)
        self.apply()
        all_results = self.search("source")["results"]
        self.assertEqual([r["record"]["item"]["id"] for r in all_results], ["ann_1", "ann_2"])
        first = self.search("source", limit=1)
        self.assertTrue(first["has_more"])
        self.assertEqual(self.search("source", limit=1, offset=1)["results"], [all_results[1]])
        self.assertEqual(self.search("source", offset=2)["results"], [])

    def test_imported_notes_search_title_body_and_linked_passages(self):
        note = {"kind": "note", "id": "note_1", "content": {
            "id": "note_1", "title": "Variance comparison", "markdown": "Donor replication matters.",
            "linkedAnnotationIds": ["ann_1"], "createdAt": fixtures.TIME, "updatedAt": fixtures.TIME},
            "passages": copy.deepcopy(self.bundle["items"][0]["passages"]),
            "provenance": copy.deepcopy(self.bundle["items"][0]["provenance"]), "review": {"status": "unreviewed"}}
        self.bundle["items"] = [note]
        self.apply(fixtures.seal(self.bundle))
        for query, field in [("variance", "title"), ("donor", "markdown"), ("synthetic", "quote")]:
            self.assertEqual(self.search(query)["results"][0]["matches"][0]["field"], field)

    def test_changed_or_missing_sources_do_not_erase_imported_text(self):
        self.apply()
        self.pdf.unlink()
        self.snapshot.unlink()
        self.assertEqual(self.search("source")["total"], 1)
        with closing(connect_db(self.db)) as conn:
            conn.execute("UPDATE notes SET content = 'locally changed'")
            conn.commit()
        result = self.search("source")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["unavailable_evidence"][0]["reason"], "imported_note_locally_edited")

    def test_corrupt_revision_fails_explicitly(self):
        self.apply()
        with closing(connect_db(self.db)) as conn:
            conn.execute("UPDATE external_evidence SET revision = 'corrupt'")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.search("source")

    def test_other_papers_are_excluded_and_original_identity_survives_merge(self):
        self.apply()
        with closing(connect_db(self.db)) as conn:
            target = PaperRepository(conn).create_paper_from_pdf(self.pdf, self.pdf, title="Other paper")
        other = copy.deepcopy(self.bundle)
        other["paper_id"] = target.id
        other["source"]["paper_ref"] = other["source"]["paper_ref"].replace(self.paper.id, target.id)
        self.apply(fixtures.seal(other))
        sha = self.bundle["document"]["sha256"]
        self.assertEqual(self.search("source")["total"], 1)
        self.assertEqual(self.search("source", paper_sources=[f"{self.paper.id}:{sha}", f"{target.id}:{sha}"])["total"], 2)
        result = run_cli("papers", "merge", target.id, self.paper.id, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        merged = self.search("source")["results"]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["paper_id"], target.id)
        self.assertEqual(merged[0]["record"]["paper_id"], self.paper.id)

    def test_invalid_filters_fail_and_read_only_cli_does_not_initialize(self):
        for kwargs in ({"paper_sources": []}, {"paper_sources": ["bad"]}, {"review": "maybe"},
                       {"limit": 0}, {"offset": -1}, {"mode": "semantic"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.search("source", **kwargs)
        args = ("note", "search-evidence", "source", "--workspace-id", "lab", "--source-id", "reader",
                "--paper-source", f"{self.paper.id}:{self.bundle['document']['sha256']}")
        absent = self.root / "absent"
        self.assertEqual(run_cli(*args, cwd=absent).returncode, 1)
        self.assertFalse(absent.exists())
        self.apply()
        before = self.state()
        result = run_cli(*args, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["total"], 1)
        self.assertEqual(before, self.state())
