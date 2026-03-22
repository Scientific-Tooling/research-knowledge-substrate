from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["RKS_DATA_DIR"] = str(cwd)
    return subprocess.run(
        [sys.executable, "-m", "rks", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class MigrationResilienceTest(unittest.TestCase):
    def test_migrate_recovers_when_reading_status_column_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            first_migrate_result = run_cli("migrate", cwd=workspace)
            self.assertEqual(first_migrate_result.returncode, 0, first_migrate_result.stderr)

            db_path = workspace / "rks.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version IN (?, ?)",
                    ("0008_paper_reading_status.sql", "0009_paper_tags.sql"),
                )
                conn.commit()

            second_migrate_result = run_cli("migrate", cwd=workspace)
            self.assertEqual(second_migrate_result.returncode, 0, second_migrate_result.stderr)
            second_payload = json.loads(second_migrate_result.stdout)
            self.assertEqual(second_payload["current_version"], "0013_merge_hypothesis_evidence_into_edges.sql")
            self.assertIn("0008_paper_reading_status.sql", second_payload["applied_migrations"])
            self.assertIn("0009_paper_tags.sql", second_payload["applied_migrations"])
