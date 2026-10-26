from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from rks.storage.db import connect_db
from tests._run_cli import run_cli


class PaperSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.data = self.root / "data"
        self.pdf = self.root / "source with spaces.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nsource bytes\n%%EOF\n")
        result = run_cli("ingest", "pdf", str(self.pdf), cwd=self.data)
        self.assertEqual(result.returncode, 0, result.stderr)
        paper = json.loads(result.stdout)
        self.paper_id = paper["id"]
        self.stored_pdf = Path(paper["pdf_path"])

    def source(self):
        return run_cli("papers", "source", self.paper_id, cwd=self.data)

    def test_identifies_exact_bytes_without_changing_database_or_migrating(self) -> None:
        database = self.data / "rks.sqlite3"
        # Removing a migration marker proves that a read does not repair schema state.
        with closing(connect_db(database)) as conn:
            conn.execute("DELETE FROM schema_migrations WHERE version = (SELECT MAX(version) FROM schema_migrations)")
            conn.commit()
            before = "\n".join(conn.iterdump())
        result = self.source()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "rks.paper-source.v1")
        self.assertEqual(payload["paper_id"], self.paper_id)
        self.assertEqual(payload["pdf"], {
            "path": str(self.stored_pdf.resolve()),
            "sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
            "size_bytes": self.pdf.stat().st_size,
        })
        with closing(connect_db(database)) as conn:
            self.assertEqual("\n".join(conn.iterdump()), before)

    def test_source_revision_changes_when_bytes_change(self) -> None:
        before = json.loads(self.source().stdout)["pdf"]["sha256"]
        self.stored_pdf.write_bytes(b"%PDF-1.4\nrevised source\n%%EOF\n")
        after = json.loads(self.source().stdout)["pdf"]["sha256"]
        self.assertNotEqual(before, after)

    def test_missing_file_is_reported(self) -> None:
        self.stored_pdf.unlink()
        result = self.source()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["type"], "FileNotFoundError")

    def test_missing_or_relative_pdf_path_is_rejected(self) -> None:
        for path in (None, "relative.pdf"):
            with self.subTest(path=path):
                with closing(connect_db(self.data / "rks.sqlite3")) as conn:
                    conn.execute("UPDATE papers SET pdf_path = ? WHERE id = ?", (path, self.paper_id))
                    conn.commit()
                result = self.source()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stderr)["type"], "ValueError")

    def test_unknown_paper_is_reported(self) -> None:
        result = run_cli("papers", "source", "p_missing", cwd=self.data)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["type"], "KeyError")

    def test_uninitialized_workspace_stays_absent(self) -> None:
        missing = self.root / "not-initialized"
        result = run_cli("papers", "source", self.paper_id, cwd=missing)
        self.assertEqual(result.returncode, 1)
        self.assertIn("rks init-db", result.stderr)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
