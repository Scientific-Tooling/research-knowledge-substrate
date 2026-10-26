from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from rks.query import QueryService
from rks.service.server import dispatch_get_request
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    DatasetRepository,
    EdgeRepository,
    MethodRepository,
    PaperRepository,
    initialize_db,
)
from rks.storage.text_search import search_records
from tests._run_cli import run_cli


def ranked(texts: list[str], query: str, mode: str = "lexical") -> list[str]:
    records = [SimpleNamespace(id=str(index), text=text) for index, text in enumerate(texts)]
    return [record.id for record in search_records(records, query, lambda record: [record.text], mode=mode)]


class TextRankingTest(unittest.TestCase):
    def test_question_terms_find_evidence_without_a_continuous_question_substring(self):
        texts = ["The study measures donor replication and sampling variance.", "The protocol uses sequencing."]
        self.assertEqual(ranked(texts, "How does donor replication affect variance?"), ["0"])
        self.assertEqual(ranked(texts, "How does donor replication affect variance?", "phrase"), [])

    def test_rank_uses_content_and_length_instead_of_record_recency(self):
        texts = ["alpha " + "background " * 40, "alpha beta", "alpha", "gamma"]
        result = ranked(texts, "alpha beta")
        self.assertEqual(result, ["1", "2", "0"])
        self.assertEqual(ranked(texts, "beta alpha alpha"), result)

    def test_union_matches_complete_tokens_and_breaks_ties_by_stable_id(self):
        self.assertEqual(ranked(["cell", "cellular", "cell"], "cell missing"), ["0", "2"])
        records = [SimpleNamespace(id="b", text="same"), SimpleNamespace(id="a", text="same")]
        self.assertEqual([record.id for record in search_records(records, "same", lambda r: [r.text])], ["a", "b"])

    def test_unicode_and_punctuation_are_text_not_query_operators(self):
        self.assertEqual(ranked(["CAFÉ ＢＥＴＡ β", "unrelated"], 'café beta β OR "NEAR*"'), ["0"])
        for query in ("", "   ", "%_\"*()", "unknown"):
            with self.subTest(query=query):
                self.assertEqual(ranked(["content", ""], query), [])
        self.assertEqual(ranked([], "query"), [])
        self.assertEqual(ranked([""], "query"), [])

    def test_phrase_is_literal_case_insensitive_and_does_not_cross_fields(self):
        self.assertEqual(ranked(["RATE 50%_A", "rate 500xa"], "50%_a", "phrase"), ["0"])
        self.assertEqual(ranked(["prefix donor replication suffix"], "DONOR REPLICATION", "phrase"), ["0"])
        records = [SimpleNamespace(id="a", name="donor", description="replication")]
        self.assertEqual(search_records(records, "donor replication", lambda r: [r.name, r.description], mode="phrase"), [])
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            ranked(["content"], "query", "misspelled")


class RepositorySearchTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        initialize_db(self.conn)
        self.papers = PaperRepository(self.conn)
        self.claims = ClaimRepository(self.conn)
        self.concepts = ConceptRepository(self.conn)
        self.methods = MethodRepository(self.conn)
        self.datasets = DatasetRepository(self.conn)
        self.query = QueryService(self.papers, self.claims, self.concepts, EdgeRepository(self.conn), self.methods, self.datasets)
        self.paper = self.papers.create_paper_from_pdf(Path("source.pdf"), Path("stored.pdf"), title="Donor replication")
        self.claim = self.claims.replace_claims_for_paper(self.paper.id, [{
            "text": "Donor replication determines sampling variance.", "predicate": "determines",
            "context": {"dataset": "Atlas", "evaluation_only": True, "passage_id": "hiddenmarker"},
        }])[0]

    def test_all_object_types_use_the_same_query_interpretation(self):
        concept = self.concepts.get_or_create("Donor replication (DR)", allow_parent=False)
        self.concepts.add_aliases(concept.id, ["Biological replicates"])
        self.methods.replace_methods_for_paper(self.paper.id, [{"name": "Replication", "description": "Donor sampling"}])
        self.datasets.replace_datasets_for_paper(self.paper.id, [{"name": "Atlas", "description": "Donor replication"}])
        payload = self.query.search("How does donor replication work?", mode="lexical")
        for group in ("papers", "claims", "concepts", "methods", "datasets"):
            with self.subTest(group=group):
                self.assertEqual(len(payload[group]), 1)
        self.assertEqual(payload["lexical_retrieval"]["method"], "bm25-terms-v1")
        self.assertEqual(self.concepts.search_concepts("biological question")[0].id, concept.id)
        self.assertEqual(self.concepts.search_concepts("DR")[0].id, concept.id)
        self.assertEqual(self.claims.search_claims("Atlas")[0].id, self.claim.id)
        for metadata in ("evaluation_only", "hiddenmarker"):
            self.assertEqual(self.claims.search_claims(metadata), [])

    def test_live_import_update_and_deletion_are_visible_without_an_index_rebuild(self):
        self.assertEqual(self.claims.search_claims("variance")[0].id, self.claim.id)
        self.claims.replace_claims_for_paper(self.paper.id, [{"text": "Protocol uses microscopy.", "predicate": "uses"}])
        self.assertEqual(self.claims.search_claims("variance"), [])
        self.assertEqual(len(self.claims.search_claims("microscopy")), 1)
        self.claims.replace_claims_for_paper(self.paper.id, [])
        self.assertEqual(self.claims.search_claims("microscopy"), [])

    def test_claims_are_searchable_by_their_linked_canonical_concept_and_alias(self):
        concept = self.concepts.get_or_create("Transformer", allow_parent=False)
        self.concepts.add_aliases(concept.id, ["Attention network"])
        self.claims.update_claim_links(self.claim.id, concept.id, None)
        self.assertEqual(self.claims.search_claims("Transformer")[0].id, self.claim.id)
        self.assertEqual(self.claims.search_claims("network architecture question")[0].id, self.claim.id)

    def test_search_is_readonly_and_phrase_has_no_silent_term_fallback(self):
        before = self.conn.total_changes
        self.conn.execute("PRAGMA query_only=ON")
        self.assertTrue(self.query.search("donor variance", mode="lexical")["claims"])
        phrase = self.query.search("donor variance", mode="phrase")
        self.assertEqual(phrase["claims"], [])
        self.assertEqual(phrase["semantic_matches"], [])
        self.assertEqual(phrase["lexical_retrieval"]["method"], "literal-phrase-v1")
        self.assertEqual(self.query.search("", mode="lexical")["claims"], [])
        self.assertEqual(self.conn.total_changes, before)
        with self.assertRaisesRegex(ValueError, "Unsupported search mode"):
            self.query.search("donor", mode="typo")


class SearchSurfaceTest(unittest.TestCase):
    def test_cli_and_http_agree_on_ranked_phrase_and_default_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "source.pdf"
            pdf.write_bytes(b"%PDF-1.4\nPlaceholder\n")
            created = run_cli("ingest", "pdf", str(pdf), cwd=root)
            self.assertEqual(created.returncode, 0, created.stderr)
            paper_id = json.loads(created.stdout)["id"]
            prepared = root / "claims.json"
            prepared.write_text(json.dumps({"claims": [
                {"text": "Protocol uses microscopy.", "predicate": "uses", "context": {"subject_text": ""},
                 "evidence": {"paper_id": paper_id}, "confidence": None},
                {"text": "Donor replication determines sampling variance.", "predicate": "determines",
                 "context": {"subject_text": ""}, "evidence": {"paper_id": paper_id}, "confidence": None},
            ]}), encoding="utf-8")
            imported = run_cli("import", "claims", paper_id, str(prepared), cwd=root)
            self.assertEqual(imported.returncode, 0, imported.stderr)
            question = "How does donor replication affect sampling variance?"
            with patch.dict(os.environ, {"RKS_DATA_DIR": temporary}):
                for mode in ("lexical", "phrase", "hybrid", "semantic"):
                    cli = run_cli("search", question, "--mode", mode, cwd=root)
                    self.assertEqual(cli.returncode, 0, cli.stderr)
                    code, _, raw = dispatch_get_request("/api/search?" + urlencode({"q": question, "mode": mode}))
                    self.assertEqual(code, 200)
                    payload = json.loads(raw)
                    self.assertEqual(payload, json.loads(cli.stdout))
                    self.assertEqual(len(payload["claims"]), 0 if mode == "phrase" else 1)
                default = run_cli("search", question, cwd=root)
                self.assertEqual(json.loads(default.stdout)["mode"], "hybrid")
                code, _, raw = dispatch_get_request("/api/search?q=donor&mode=typo")
                self.assertEqual(code, 400)
                self.assertEqual(json.loads(raw)["error"], "invalid_search_mode")
            invalid = run_cli("search", question, "--mode", "typo", cwd=root)
            self.assertEqual(invalid.returncode, 2)
