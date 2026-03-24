"""Claim extraction quality regression tests (roadmap Phase 1 P0-1).

Each test corresponds to one golden file in tests/golden/.  The test ingests
the matching paper fixture, imports pre-seeded claims via the agent path, then
runs ``rks evaluate claims`` against the golden set and asserts the F1 score
meets the threshold recorded in the golden file.

Purpose
-------
This test file is the CI quality gate for extraction quality.  A failing test
means extraction quality has regressed below the annotated baseline for that
paper.  Raise the threshold in the golden file when quality genuinely improves,
not as a workaround.

Adding a new paper
------------------
1. Annotate claims for your paper in a new ``tests/golden/<paper_slug>.json``
   following the schema below.
2. Add a corresponding ``_load_fixture`` block in ``_FIXTURES`` at the bottom
   of this file that pairs the golden slug to its paper text and agent-claims
   result.
3. Run locally with ``python -m pytest tests/test_claim_quality_regression.py -v``
   and confirm the baseline passes before merging.

Golden file schema
------------------
{
  "paper_fixture": "<slug matching a key in _FIXTURES>",
  "min_f1":        <float threshold, 0.0–1.0>,
  "claims":        ["<golden claim text>", ...]
}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).parent / "golden"

# ---------------------------------------------------------------------------
# Paper fixtures: slug → (paper_text, agent_text_result, agent_claims_result)
# ---------------------------------------------------------------------------

_SAMPLE_TRANSFORMER_TEXT = (
    "Transformers improve translation accuracy on WMT14. "
    "The attention mechanism allows the model to focus on relevant source tokens. "
    "We report a BLEU score of 28.4 on the English-to-German translation task."
)

_FIXTURES: dict[str, dict] = {
    "sample_transformer_paper": {
        "paper_text": _SAMPLE_TRANSFORMER_TEXT,
        "agent_text_result": {
            "text": _SAMPLE_TRANSFORMER_TEXT,
            "paragraphs": [_SAMPLE_TRANSFORMER_TEXT],
            "warnings": [],
        },
        "agent_claims_result": {
            "claims": [
                {
                    "text": "Transformers improve translation accuracy on WMT14.",
                    "predicate": "improves",
                    "object_text": "translation accuracy",
                    "context": {
                        "subject_text": "Transformers",
                        "dataset": "WMT14",
                        "section": "abstract",
                    },
                    "evidence": {"extraction": "agent"},
                    "confidence": 0.92,
                },
                {
                    "text": "The attention mechanism allows the model to focus on relevant source tokens.",
                    "predicate": "allows",
                    "object_text": "focus on relevant source tokens",
                    "context": {
                        "subject_text": "attention mechanism",
                        "section": "method",
                    },
                    "evidence": {"extraction": "agent"},
                    "confidence": 0.88,
                },
            ]
        },
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
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


def _load_golden_files() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*.json"))


def _setup_paper(tmp: Path, fixture: dict) -> str:
    """Ingest + import text + import claims for a fixture; return paper_id."""
    pdf_path = tmp / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n" + fixture["paper_text"].encode() + b"\n")

    ingest = _run_cli("ingest", "pdf", str(pdf_path), cwd=tmp)
    assert ingest.returncode == 0, ingest.stderr
    paper_id: str = json.loads(ingest.stdout)["id"]

    # Import text via agent fixture.
    text_req = _run_cli("extract", "text", paper_id, "--mode", "agent", cwd=tmp)
    assert text_req.returncode == 0, text_req.stderr

    text_result_path = tmp / "agent_text_result.json"
    text_result_path.write_text(
        json.dumps(fixture["agent_text_result"]), encoding="utf-8"
    )
    import_text = _run_cli("import", "text", paper_id, str(text_result_path), cwd=tmp)
    assert import_text.returncode == 0, import_text.stderr

    # Import claims via agent fixture.
    _run_cli("extract", "claims", paper_id, "--mode", "agent", cwd=tmp)

    claims_result = json.loads(json.dumps(fixture["agent_claims_result"]))
    for claim in claims_result["claims"]:
        claim["evidence"]["paper_id"] = paper_id

    claims_result_path = tmp / "agent_claims_result.json"
    claims_result_path.write_text(json.dumps(claims_result), encoding="utf-8")
    import_claims = _run_cli(
        "import", "claims", paper_id, str(claims_result_path), cwd=tmp
    )
    assert import_claims.returncode == 0, import_claims.stderr

    return paper_id


# ---------------------------------------------------------------------------
# Test generation: one test method per golden file
# ---------------------------------------------------------------------------

def _make_regression_test(golden_path: Path):
    def test_method(self: unittest.TestCase) -> None:
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        slug = golden["paper_fixture"]
        min_f1 = float(golden["min_f1"])

        if slug not in _FIXTURES:
            self.skipTest(
                f"No fixture registered for '{slug}' — add it to _FIXTURES in "
                "tests/test_claim_quality_regression.py"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paper_id = _setup_paper(tmp, _FIXTURES[slug])

            golden_file = tmp / "golden.json"
            golden_file.write_text(
                json.dumps(golden["claims"]), encoding="utf-8"
            )

            result = _run_cli(
                "evaluate", "claims", paper_id,
                "--golden", str(golden_file),
                "--min-f1", str(min_f1),
                cwd=tmp,
            )
            payload = json.loads(result.stdout) if result.stdout.strip() else {}

            self.assertEqual(
                result.returncode, 0,
                f"F1 regression for '{golden_path.name}': "
                f"f1={payload.get('f1', '?'):.3f} < threshold={min_f1}. "
                f"stderr: {result.stderr}",
            )
            self.assertGreaterEqual(
                payload.get("f1", 0.0), min_f1,
                f"F1 {payload.get('f1', 0.0):.3f} is below threshold {min_f1} "
                f"for golden set '{golden_path.name}'.",
            )

    test_method.__name__ = f"test_quality_regression_{golden_path.stem}"
    test_method.__doc__ = f"Claim quality regression: {golden_path.name} (min_f1={json.loads(golden_path.read_text())['min_f1']})"
    return test_method


class ClaimQualityRegressionTests(unittest.TestCase):
    pass


for _golden_path in _load_golden_files():
    _test_fn = _make_regression_test(_golden_path)
    setattr(ClaimQualityRegressionTests, _test_fn.__name__, _test_fn)


if __name__ == "__main__":
    unittest.main()
