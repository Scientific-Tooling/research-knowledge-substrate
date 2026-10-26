from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from rks.cli._context import _doctor_recommended_actions
from rks.cli.main import main


class DoctorConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.home_patch = patch("pathlib.Path.home", return_value=self.root / "home")
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.env_patch = patch.dict(os.environ)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        os.environ.pop("RKS_DATA_DIR", None)

    def cli(self, *args: str) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(list(args)), 0)
        return json.loads(output.getvalue())

    def test_unconfigured_workspace_recommends_initialization_without_writes(self) -> None:
        result = self.cli("doctor")
        self.assertIsNone(result["checks"]["configuration"]["source"])
        self.assertEqual(result["recommended_actions"], ["rks init <path>  # set your data directory"])
        self.assertFalse((self.root / "home").exists())

    def test_environment_override_does_not_require_global_config(self) -> None:
        os.environ["RKS_DATA_DIR"] = str(self.root / "data")
        before = self.cli("doctor")
        self.assertEqual(before["checks"]["configuration"]["source"], "environment")
        self.assertFalse(before["checks"]["global_config"]["required"])
        self.assertEqual(before["recommended_actions"], ["rks init-db"])
        self.assertFalse((self.root / "data").exists())
        self.cli("init-db")
        after = self.cli("doctor")
        self.assertEqual(after["overall_status"], "ok")
        self.assertFalse((self.root / "home").exists())

    def test_global_configuration_is_reported_as_effective_source(self) -> None:
        self.cli("init", str(self.root / "global-data"))
        result = self.cli("doctor")
        self.assertEqual(result["checks"]["configuration"]["source"], "global_config")
        self.assertTrue(result["checks"]["global_config"]["ok"])
        self.assertEqual(result["overall_status"], "ok")

    def test_environment_override_ignores_unused_malformed_global_file(self) -> None:
        config = self.root / "home" / ".rks" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text("{invalid", encoding="utf-8")
        os.environ["RKS_DATA_DIR"] = str(self.root / "override")
        self.assertEqual(self.cli("doctor")["recommended_actions"], ["rks init-db"])

    def test_independent_database_problems_are_not_hidden(self) -> None:
        actions = _doctor_recommended_actions({
            "configuration": {"ok": True},
            "data_dir": {"ok": False},
            "database": {"ok": True},
            "database_integrity": {"ok": False},
        })
        self.assertIn("rks init-db", actions)
        self.assertTrue(any("orphaned database rows" in action for action in actions))


if __name__ == "__main__":
    unittest.main()
