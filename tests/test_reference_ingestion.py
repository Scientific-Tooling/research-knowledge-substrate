from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from rks.config import AppPaths
from rks.ingestion.reference import (
    ingest_arxiv_reference,
    ingest_doi_reference,
    ingest_pmid_reference,
    ingest_url_reference,
    resolve_reference_url,
)
from rks.providers import PubmedMetadataProvider
from rks.service import dispatch_get_request
from rks.storage import PaperRepository, connect_db, initialize_db


class _FakeProvider:
    def __init__(self, payload: dict):
        self.payload = payload

    def fetch(self, _identifier: str) -> dict:
        return self.payload


class ReferenceIngestionTest(unittest.TestCase):
    def _make_repo(self) -> tuple[Path, AppPaths, object, PaperRepository]:
        tmp_dir = tempfile.TemporaryDirectory()
        root = Path(tmp_dir.name)
        paths = AppPaths(
            root=root,
            data_dir=root / "data",
            papers_dir=root / "data" / "papers",
            artifacts_dir=root / "data" / "artifacts",
            db_path=root / "data" / "rks.sqlite3",
        )
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        conn = connect_db(paths.db_path)
        initialize_db(conn)
        return root, paths, tmp_dir, PaperRepository(conn)

    def test_pubmed_metadata_provider_parses_pubmed_xml(self) -> None:
        raw_xml = """
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <Article>
                <ArticleTitle>Structured extraction for literature agents</ArticleTitle>
                <Abstract>
                  <AbstractText Label="BACKGROUND">The first section.</AbstractText>
                  <AbstractText>The second section.</AbstractText>
                </Abstract>
                <Journal>
                  <Title>Journal of Testing</Title>
                  <JournalIssue>
                    <PubDate>
                      <MedlineDate>2024 Jan-Feb</MedlineDate>
                    </PubDate>
                  </JournalIssue>
                </Journal>
                <AuthorList>
                  <Author>
                    <ForeName>Ada</ForeName>
                    <LastName>Lovelace</LastName>
                  </Author>
                  <Author>
                    <CollectiveName>The RKS Consortium</CollectiveName>
                  </Author>
                </AuthorList>
              </Article>
            </MedlineCitation>
            <PubmedData>
              <ArticleIdList>
                <ArticleId IdType="pubmed">12345678</ArticleId>
                <ArticleId IdType="doi">10.1000/example</ArticleId>
              </ArticleIdList>
              <ReferenceList>
                <Reference>
                  <Citation>Earlier Work. 2019.</Citation>
                  <ArticleIdList>
                    <ArticleId IdType="doi">10.1000/earlier</ArticleId>
                  </ArticleIdList>
                </Reference>
              </ReferenceList>
            </PubmedData>
          </PubmedArticle>
        </PubmedArticleSet>
        """

        def fake_urlopen(url: str):
            self.assertIn("db=pubmed", url)
            self.assertIn("id=12345678", url)
            return io.BytesIO(raw_xml.encode("utf-8"))

        payload = PubmedMetadataProvider(urlopen=fake_urlopen).fetch("12345678")
        self.assertEqual(payload["title"], "Structured extraction for literature agents")
        self.assertEqual(payload["abstract"], "BACKGROUND: The first section.\n\nThe second section.")
        self.assertEqual(payload["authors"], ["Ada Lovelace", "The RKS Consortium"])
        self.assertEqual(payload["year"], 2024)
        self.assertEqual(payload["venue"], "Journal of Testing")
        self.assertEqual(payload["doi"], "10.1000/example")
        self.assertEqual(payload["references"][0]["doi"], "10.1000/earlier")

    def test_reference_ingestion_downloads_source_pdf_and_exposes_status(self) -> None:
        root, paths, tmp_dir, repo = self._make_repo()
        try:
            paper = ingest_doi_reference(
                repo=repo,
                paths=paths,
                doi="10.1000/example",
                provider=_FakeProvider(
                    {
                        "title": "Example DOI Paper",
                        "abstract": "A short abstract for testing.",
                        "authors": ["Ada Lovelace"],
                        "year": 2024,
                        "venue": "TestConf",
                        "doi": "10.1000/example",
                        "arxiv_id": None,
                        "references": [],
                        "pdf_candidates": [{"url": "https://example.org/paper.pdf", "source": "test"}],
                        "raw": {"ok": True},
                    }
                ),
                downloader=lambda url: b"%PDF-1.4\nDownloaded from " + url.encode("utf-8"),
            )

            artifacts = repo.get_artifacts_for_paper(paper.id)
            artifact_types = {artifact.artifact_type for artifact in artifacts}
            self.assertIn("source_pdf", artifact_types)
            self.assertIn("source_pdf_acquisition", artifact_types)
            self.assertTrue(Path(paper.pdf_path).exists())

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                _, _, status_body = dispatch_get_request(f"/api/status/{paper.id}")
            finally:
                os.chdir(previous_cwd)
            status_payload = json.loads(status_body.decode("utf-8"))
            self.assertTrue(status_payload["source_pdf"]["available"])
            self.assertEqual(status_payload["source_pdf"]["acquisition"]["status"], "downloaded")
            self.assertEqual(
                status_payload["source_pdf"]["acquisition"]["downloaded_from"],
                "https://example.org/paper.pdf",
            )
        finally:
            repo.conn.close()
            tmp_dir.cleanup()

    def test_reference_ingestion_records_skipped_acquisition(self) -> None:
        root, paths, tmp_dir, repo = self._make_repo()
        try:

            paper = ingest_arxiv_reference(
                repo=repo,
                paths=paths,
                arxiv_id="1234.5678",
                provider=_FakeProvider(
                    {
                        "title": "Example arXiv Paper",
                        "abstract": None,
                        "authors": ["Grace Hopper"],
                        "year": 2025,
                        "venue": "arXiv",
                        "doi": None,
                        "arxiv_id": "1234.5678",
                        "references": [],
                        "pdf_candidates": [{"url": "https://arxiv.org/pdf/1234.5678.pdf", "source": "arxiv_pdf"}],
                        "raw": "<xml />",
                    }
                ),
                acquire_pdf=False,
            )

            artifacts = repo.get_artifacts_for_paper(paper.id)
            acquisition_artifact = next(
                artifact for artifact in artifacts if artifact.artifact_type == "source_pdf_acquisition"
            )
            payload = json.loads(acquisition_artifact.metadata_json)
            self.assertEqual(payload["status"], "skipped")
            self.assertFalse(repo.get_paper(paper.id).pdf_path)
            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                _, _, status_body = dispatch_get_request(f"/api/status/{paper.id}")
            finally:
                os.chdir(previous_cwd)
            status_payload = json.loads(status_body.decode("utf-8"))
            self.assertEqual(status_payload["readiness"]["current_level"], "ingested")
            self.assertIn("source_pdf_unavailable", {item["code"] for item in status_payload["missing_steps"]})
            self.assertIn("no_local_source_pdf", {item["code"] for item in status_payload["blockers"]})
            self.assertIn(f"rks ingest arxiv {paper.arxiv_id}", status_payload["suggested_next_commands"])
        finally:
            repo.conn.close()
            tmp_dir.cleanup()

    def test_pmid_reference_ingestion_persists_xml_metadata(self) -> None:
        _, paths, tmp_dir, repo = self._make_repo()
        try:
            paper = ingest_pmid_reference(
                repo=repo,
                paths=paths,
                pmid="31452104",
                provider=_FakeProvider(
                    {
                        "title": "PubMed Example Paper",
                        "abstract": "A PubMed abstract.",
                        "authors": ["Rosalind Franklin"],
                        "year": 2019,
                        "venue": "PubMed Journal",
                        "doi": "10.1000/pubmed",
                        "arxiv_id": None,
                        "references": [],
                        "pdf_candidates": [],
                        "raw": "<PubmedArticleSet />",
                    }
                ),
                acquire_pdf=False,
            )

            self.assertEqual(paper.source_type, "pmid")
            self.assertEqual(paper.source_ref, "31452104")
            self.assertEqual(paper.doi, "10.1000/pubmed")
            artifacts = repo.get_artifacts_for_paper(paper.id)
            metadata_artifact = next(artifact for artifact in artifacts if artifact.artifact_type == "metadata")
            self.assertTrue(metadata_artifact.path.endswith("metadata.xml"))
            self.assertEqual(metadata_artifact.format, "xml")
            self.assertIsNotNone(paper.text_artifact_id)
        finally:
            repo.conn.close()
            tmp_dir.cleanup()

    def test_url_reference_dispatches_pubmed_urls(self) -> None:
        _, paths, tmp_dir, repo = self._make_repo()
        try:
            paper = ingest_url_reference(
                repo=repo,
                paths=paths,
                url="https://pubmed.ncbi.nlm.nih.gov/31452104/",
                crossref_provider=_FakeProvider({}),
                arxiv_provider=_FakeProvider({}),
                pubmed_provider=_FakeProvider(
                    {
                        "title": "PubMed URL Paper",
                        "abstract": None,
                        "authors": [],
                        "year": 2020,
                        "venue": "PubMed",
                        "doi": None,
                        "arxiv_id": None,
                        "references": [],
                        "pdf_candidates": [],
                        "raw": "<PubmedArticleSet />",
                    }
                ),
                acquire_pdf=False,
            )

            self.assertEqual(paper.source_type, "pmid")
            self.assertEqual(paper.source_ref, "31452104")
            self.assertEqual(paper.title, "PubMed URL Paper")
        finally:
            repo.conn.close()
            tmp_dir.cleanup()

    def test_url_reference_preserves_legacy_arxiv_identifiers(self) -> None:
        _, paths, tmp_dir, repo = self._make_repo()
        try:
            metadata = {
                "title": "Legacy arXiv Paper",
                "abstract": "Legacy abstract.",
                "authors": ["Grace Hopper"],
                "year": 2001,
                "venue": "arXiv",
                "doi": None,
                "arxiv_id": "cs/0112017",
                "references": [{"title": "Earlier work"}],
                "pdf_candidates": [],
                "raw": "<entry />",
            }

            abs_paper = ingest_url_reference(
                repo=repo,
                paths=paths,
                url="https://arxiv.org/abs/cs/0112017",
                crossref_provider=_FakeProvider({}),
                arxiv_provider=_FakeProvider(metadata),
                pubmed_provider=_FakeProvider({}),
                acquire_pdf=False,
            )
            pdf_resolution = resolve_reference_url("https://arxiv.org/pdf/cs/0112017.pdf")

            self.assertEqual(abs_paper.source_type, "arxiv")
            self.assertEqual(abs_paper.source_ref, "cs/0112017")
            self.assertEqual(abs_paper.arxiv_id, "cs/0112017")
            self.assertEqual(abs_paper.title, "Legacy arXiv Paper")
            self.assertEqual(pdf_resolution.kind, "arxiv")
            self.assertEqual(pdf_resolution.value, "cs/0112017")
        finally:
            repo.conn.close()
            tmp_dir.cleanup()

    def test_url_reference_ingests_direct_pdf_urls(self) -> None:
        _, paths, tmp_dir, repo = self._make_repo()
        try:
            paper = ingest_url_reference(
                repo=repo,
                paths=paths,
                url="https://example.org/papers/remote-paper.pdf",
                crossref_provider=_FakeProvider({}),
                arxiv_provider=_FakeProvider({}),
                pubmed_provider=_FakeProvider({}),
                downloader=lambda _: b"%PDF-1.4\nRemote PDF content.\n",
            )

            self.assertEqual(paper.source_type, "pdf")
            self.assertEqual(paper.source_ref, "https://example.org/papers/remote-paper.pdf")
            self.assertEqual(paper.title, "remote-paper")
            self.assertTrue(Path(paper.pdf_path).exists())
            self.assertIsNotNone(paper.text_artifact_id)
        finally:
            repo.conn.close()
            tmp_dir.cleanup()

    def test_url_reference_ingests_pdf_endpoints_without_pdf_suffix(self) -> None:
        _, paths, tmp_dir, repo = self._make_repo()
        try:
            paper = ingest_url_reference(
                repo=repo,
                paths=paths,
                url="https://example.org/doi/pdf/10.1000/example",
                crossref_provider=_FakeProvider({}),
                arxiv_provider=_FakeProvider({}),
                pubmed_provider=_FakeProvider({}),
                downloader=lambda _: b"%PDF-1.4\nRemote PDF content.\n",
            )

            self.assertEqual(paper.source_type, "pdf")
            self.assertEqual(paper.source_ref, "https://example.org/doi/pdf/10.1000/example")
            self.assertEqual(paper.title, "example")
            self.assertTrue(Path(paper.pdf_path).exists())
            self.assertIsNotNone(paper.text_artifact_id)
        finally:
            repo.conn.close()
            tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
