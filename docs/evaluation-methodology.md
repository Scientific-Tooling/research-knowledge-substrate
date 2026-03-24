# Claim Extraction Evaluation Methodology

This document describes how RKS measures and enforces claim extraction quality through its golden-set evaluation system.

## Overview

Claim extraction quality is measured by comparing extracted claims against a human-annotated golden set for each paper. The comparison uses token-set Jaccard similarity to allow for minor wording differences without requiring exact string matches. Precision, recall, and F1 are reported for each paper.

The evaluation runs automatically in CI (`package-check.yml`) on every commit, acting as a regression gate. A failing test means extraction quality has dropped below the annotated baseline.

## Metrics

| Metric | Definition |
|--------|-----------|
| Precision | fraction of extracted claims that match a golden claim |
| Recall | fraction of golden claims matched by at least one extracted claim |
| F1 | harmonic mean of precision and recall |

A golden claim is considered **matched** if any extracted claim has a Jaccard token similarity score ≥ 0.3 (configurable via `match_threshold` in `_evaluate_claims_against_golden`).

## Golden Set File Format

Golden files live in `tests/golden/` and follow this schema:

```json
{
  "_comment": "optional free-text note",
  "paper_fixture": "<slug matching a key in tests/test_claim_quality_regression._FIXTURES>",
  "min_f1": 0.6,
  "claims": [
    "Claim text as it should appear in the extracted output.",
    "Another expected claim."
  ]
}
```

`min_f1` is the CI threshold for this paper. Evaluation exits 1 (CI fails) when the measured F1 is below this value.

## Adding a New Paper to the Golden Set

1. **Annotate claims.** Read the paper and write down the most important factual claims — one sentence each. Aim for 5–15 claims covering abstract, methods, and results sections. Prefer the paper's own phrasing where possible, since the extractor aims to reproduce it.

2. **Create the golden file.** Save to `tests/golden/<paper_slug>.json` following the schema above. Choose `min_f1` based on the extraction mode you expect to use (start at 0.5 for `agent` mode; raise it once you measure the baseline).

3. **Register the fixture.** Add an entry to `_FIXTURES` in `tests/test_claim_quality_regression.py`:

   ```python
   "my_paper_slug": {
       "paper_text": "<full text of the paper or representative excerpt>",
       "agent_text_result": { ... },   # see existing fixture for schema
       "agent_claims_result": { ... }, # see existing fixture for schema
   }
   ```

   The `agent_claims_result` should reflect the current best extraction for this paper so the test measures the right baseline.

4. **Run locally and set the threshold.**

   ```bash
   python -m pytest tests/test_claim_quality_regression.py -v
   ```

   Observe the F1 value in the output. Set `min_f1` in the golden file to this measured value (or slightly below, e.g. −0.05, to allow for minor variation). Do not set `min_f1` higher than the current measured F1, or the test will fail immediately.

5. **Commit both files** (golden JSON + any fixture addition to the test file) together. The CI regression will now enforce this paper's quality baseline on every future commit.

## Running the Evaluation Locally

Against the full golden set (same as CI):

```bash
python -m pytest tests/test_claim_quality_regression.py -v
```

Against a single paper with live CLI output:

```bash
rks evaluate claims <paper_id> --golden tests/golden/<paper_slug>.json --min-f1 0.5
```

The command prints a JSON payload:

```json
{
  "paper_id": "p_000001",
  "golden_count": 8,
  "actual_count": 11,
  "true_positives": 6,
  "precision": 0.545,
  "recall": 0.75,
  "f1": 0.632,
  "passed": true,
  "pairs": [
    {
      "golden": "Transformers improve translation accuracy on WMT14.",
      "best_match": "Transformers improve translation accuracy on WMT14.",
      "score": 1.0,
      "matched": true
    }
  ]
}
```

## Updating the Threshold

Raise `min_f1` in a golden file only when extraction quality has genuinely improved (e.g. after a prompt change, a new extractor version, or a richer agent result). Do not raise it to suppress a failing test caused by a regression — fix the regression instead.

Lower `min_f1` only when you have intentionally changed the extraction scope for a paper (e.g. switched from `agent` to `llm-api` mode and measured the new baseline).

## CI Wiring

The CI workflow (`package-check.yml`) runs `python -m unittest discover -s tests -v`, which discovers `test_claim_quality_regression.py` automatically. No additional CI configuration is needed when a new golden file is added — as long as the matching fixture is registered in `_FIXTURES`, the test is picked up on the next CI run.

## Current Baseline Status

The golden set now includes one real domain paper (GLOBOCAN 2020) with 13 annotated claims. Expand to 5–10 papers to complete roadmap Phase 1 P0-1.

| Golden file | Paper | `min_f1` | Status |
|-------------|-------|----------|--------|
| `sample_transformer_paper.json` | Synthetic fixture — demonstrates format | 0.5 | Active in CI |
| `globocan_2020.json` | Sung et al. 2021 — Global Cancer Statistics 2020 (GLOBOCAN), CA Cancer J Clin 71:209-249. 13 annotated claims covering abstract, results, discussion. Baseline F1 = 0.788 (precision 0.65, recall 1.0) using agent-mode extraction. | 0.75 | Active in CI |
