"""Separate prepared-import contract checks from heuristic extraction checks.

Each golden file exercises two paths: importing prepared agent claims and
running the heuristic extractor on fixture text. Neither path invokes a live
agent or API model. The import path validates storage and scoring contracts;
only the heuristic path measures actual extraction from these text fixtures.

Purpose
-------
Thresholds preserve measured fixture baselines. They are not scientific
release criteria or evidence of live model quality.

Adding a new paper
------------------
1. Annotate claims for your paper in a new ``tests/golden/<paper_slug>.json``
   following the schema below.
2. Add a corresponding entry in ``_FIXTURES`` that pairs the golden slug to
   its paper text and prepared agent-claims result.
3. Run locally with ``python -m pytest tests/test_claim_quality_regression.py -v``
   and confirm the baseline passes before merging.

Golden file schema
------------------
{
  "paper_fixture": "<slug matching a key in _FIXTURES>",
  "min_f1":        <float threshold, 0.0–1.0>,
  "heuristic_min_f1": <measured heuristic regression threshold>,
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
from unittest.mock import patch

from rks.cli._context import _open_session
from rks.config import load_paths
from rks.extraction.claims import extract_claims_for_paper


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

_GLOBOCAN_2020_TEXT = (
    "Worldwide, an estimated 19.3 million new cancer cases (18.1 million excluding nonmelanoma skin cancer) "
    "and almost 10.0 million cancer deaths (9.9 million excluding nonmelanoma skin cancer) occurred in 2020. "
    "Female breast cancer has surpassed lung cancer as the most commonly diagnosed cancer, with an estimated "
    "2.3 million new cases (11.7%). Lung cancer remained the leading cause of cancer death, with an estimated "
    "1.8 million deaths (18%). The global cancer burden is expected to be 28.4 million cases in 2040, a 47% rise "
    "from 2020. Overall incidence was from 2-fold to 3-fold higher in transitioned versus transitioning countries "
    "for both sexes. One in 5 men or women develop the disease, and 1 in 8 men and 1 in 11 women die from it. "
    "cancer is the first or second leading cause of death before the age of 70 years in 112 of 183 countries. "
    "HBV infection and HCV infection account for 56% and 20% of liver cancer deaths worldwide, respectively. "
    "Rates remain disproportionately high in transitioning versus transitioned countries (18.8 vs 11.3 per 100,000 "
    "for incidence; 12.4 vs 5.2 per 100,000 for mortality). The relative magnitude of increase is most striking "
    "in low HDI countries (95%) and in medium HDI countries (64%)."
)

_FIXTURES: dict[str, dict] = {
    "globocan_2020": {
        "paper_text": _GLOBOCAN_2020_TEXT,
        "agent_text_result": {
            "text": _GLOBOCAN_2020_TEXT,
            "paragraphs": [_GLOBOCAN_2020_TEXT],
            "warnings": [],
        },
        "agent_claims_result": {
            "claims": [
                {
                    "text": "Worldwide, an estimated 19.3 million new cancer cases and almost 10.0 million cancer deaths occurred in 2020.",
                    "predicate": "occurred",
                    "object_text": "19.3 million new cancer cases and almost 10.0 million cancer deaths",
                    "context": {"subject_text": "global cancer burden", "section": "abstract", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "Worldwide, an estimated 19.3 million new cancer cases (18.1 million excluding nonmelanoma skin cancer) and almost 10.0 million cancer deaths (9.9 million excluding nonmelanoma skin cancer) occurred in 2020."},
                    "confidence": 0.99,
                },
                {
                    "text": "Female breast cancer has surpassed lung cancer as the most commonly diagnosed cancer globally in 2020, with an estimated 2.3 million new cases (11.7%).",
                    "predicate": "surpassed",
                    "object_text": "lung cancer as the most commonly diagnosed cancer globally",
                    "context": {"subject_text": "female breast cancer", "section": "abstract", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "Female breast cancer has surpassed lung cancer as the most commonly diagnosed cancer, with an estimated 2.3 million new cases (11.7%)"},
                    "confidence": 0.99,
                },
                {
                    "text": "Lung cancer remained the leading cause of cancer death globally in 2020, with an estimated 1.8 million deaths (18%).",
                    "predicate": "remained",
                    "object_text": "leading cause of cancer death globally",
                    "context": {"subject_text": "lung cancer", "section": "abstract", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "Lung cancer remained the leading cause of cancer death, with an estimated 1.8 million deaths (18%)"},
                    "confidence": 0.99,
                },
                {
                    "text": "The global cancer burden is expected to reach 28.4 million cases in 2040, a 47% rise from 2020.",
                    "predicate": "expected to reach",
                    "object_text": "28.4 million cases in 2040",
                    "context": {"subject_text": "global cancer burden", "section": "abstract", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "The global cancer burden is expected to be 28.4 million cases in 2040, a 47% rise from 2020"},
                    "confidence": 0.98,
                },
                {
                    "text": "Cancer is the first or second leading cause of premature death before age 70 in 112 of 183 countries.",
                    "predicate": "is",
                    "object_text": "first or second leading cause of premature death in 112 of 183 countries",
                    "context": {"subject_text": "cancer", "section": "introduction", "dataset": None},
                    "evidence": {"extraction": "agent", "quote": "cancer is the first or second leading cause of death before the age of 70 years in 112 of 183 countries"},
                    "confidence": 0.99,
                },
                {
                    "text": "Overall cancer incidence was 2-fold to 3-fold higher in transitioned versus transitioning countries for both sexes.",
                    "predicate": "was higher in",
                    "object_text": "transitioned versus transitioning countries",
                    "context": {"subject_text": "overall cancer incidence", "section": "abstract", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "Overall incidence was from 2-fold to 3-fold higher in transitioned versus transitioning countries for both sexes"},
                    "confidence": 0.98,
                },
                {
                    "text": "Asia accounted for approximately 49.3% of all cancer cases and 58.3% of cancer deaths globally in 2020.",
                    "predicate": "accounted for",
                    "object_text": "49.3% of cancer cases and 58.3% of cancer deaths globally",
                    "context": {"subject_text": "Asia", "section": "results", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "one-half of all cases and 58.3% of cancer deaths are estimated to occur in Asia in 2020"},
                    "confidence": 0.99,
                },
                {
                    "text": "One in 5 men or women will develop cancer in their lifetime, and 1 in 8 men and 1 in 11 women will die from it.",
                    "predicate": "will develop",
                    "object_text": "cancer in their lifetime",
                    "context": {"subject_text": "global population", "section": "results", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "One in 5 men or women develop the disease, and 1 in 8 men and 1 in 11 women die from it."},
                    "confidence": 0.99,
                },
                {
                    "text": "Approximately two-thirds of lung cancer deaths worldwide are attributable to smoking.",
                    "predicate": "attributable to",
                    "object_text": "smoking",
                    "context": {"subject_text": "lung cancer deaths", "section": "results", "dataset": None},
                    "evidence": {"extraction": "agent", "quote": "With about two-thirds of lung cancer deaths worldwide attributable to smoking, the disease can be largely prevented through effective tobacco-control policies and regulations."},
                    "confidence": 0.99,
                },
                {
                    "text": "HBV infection and HCV infection account for 56% and 20% of liver cancer deaths worldwide, respectively.",
                    "predicate": "account for",
                    "object_text": "56% and 20% of liver cancer deaths worldwide",
                    "context": {"subject_text": "Hepatitis B Virus and Hepatitis C Virus", "section": "results", "dataset": None},
                    "evidence": {"extraction": "agent", "quote": "HBV infection and HCV infection account for 56% and 20% of liver cancer deaths worldwide, respectively."},
                    "confidence": 0.99,
                },
                {
                    "text": "Cervical cancer incidence rates remain disproportionately high in transitioning versus transitioned countries (18.8 vs 11.3 per 100,000).",
                    "predicate": "remain higher in",
                    "object_text": "transitioning versus transitioned countries",
                    "context": {"subject_text": "cervical cancer incidence rates", "section": "results", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "Rates remain disproportionately high in transitioning versus transitioned countries (18.8 vs 11.3 per 100,000 for incidence; 12.4 vs 5.2 per 100,000 for mortality)"},
                    "confidence": 0.99,
                },
                {
                    "text": "As of May 2020, less than 30% of LMICs had implemented national HPV vaccination programs, compared with over 80% of high-income countries.",
                    "predicate": "implemented",
                    "object_text": "national HPV vaccination programs",
                    "context": {"subject_text": "low- and middle-income countries", "section": "results", "dataset": None},
                    "evidence": {"extraction": "agent", "quote": "As of May 2020, <30% of LMICs had implemented national HPV vaccination programs compared with >80% of high-income countries."},
                    "confidence": 0.99,
                },
                {
                    "text": "Low HDI countries are projected to see a 95% increase in cancer cases by 2040, and medium HDI countries a 64% increase.",
                    "predicate": "are projected to see",
                    "object_text": "95% increase in cancer cases by 2040",
                    "context": {"subject_text": "low HDI countries", "section": "results", "dataset": "GLOBOCAN 2020"},
                    "evidence": {"extraction": "agent", "quote": "The relative magnitude of increase is most striking in low HDI countries (95%) and in medium HDI countries (64%)."},
                    "confidence": 0.98,
                },
            ]
        },
    },
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


def _setup_paper(tmp: Path, fixture: dict, mode: str = "prepared-import") -> str:
    """Import source text, then extract or import claims; return paper_id."""
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

    if mode == "heuristic":
        # The CLI exposes agent/API modes; exercise the deterministic library
        # extractor directly, then score its persisted output through the CLI.
        with patch.dict(os.environ, {"RKS_DATA_DIR": str(tmp)}), _open_session() as session:
            extract_claims_for_paper(
                paths=load_paths(), paper_repo=session.papers, claim_repo=session.claims,
                concept_repo=session.concepts, edge_repo=session.edges, paper_id=paper_id,
            )
        return paper_id

    # Prepared claims validate import behavior, not a live agent's extraction.
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

def _make_regression_test(golden_path: Path, mode: str):
    def test_method(self: unittest.TestCase) -> None:
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        slug = golden["paper_fixture"]
        threshold_key = "heuristic_min_f1" if mode == "heuristic" else "min_f1"
        min_f1 = float(golden[threshold_key])

        if slug not in _FIXTURES:
            self.fail(
                f"No fixture registered for '{slug}' — add it to _FIXTURES in "
                "tests/test_claim_quality_regression.py"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paper_id = _setup_paper(tmp, _FIXTURES[slug], mode=mode)

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
            self.assertLessEqual(payload["f1"], 1.0)
            self.assertEqual(payload["matching_policy"], "one-to-one-max-cardinality-v1")

    test_method.__name__ = f"test_{mode.replace('-', '_')}_{golden_path.stem}"
    test_method.__doc__ = f"{mode} fixture regression: {golden_path.name}"
    return test_method


class ClaimQualityRegressionTests(unittest.TestCase):
    pass


for _golden_path in _load_golden_files():
    for _mode in ("prepared-import", "heuristic"):
        _test_fn = _make_regression_test(_golden_path, _mode)
        setattr(ClaimQualityRegressionTests, _test_fn.__name__, _test_fn)


if __name__ == "__main__":
    unittest.main()
