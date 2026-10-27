# Claim evaluation methodology

RKS evaluates lexical claim coverage separately from scientific correctness.
The current fixtures exercise prepared claim imports and deterministic heuristic
extraction. They do not measure a live agent or API model's performance.

## Matching and metrics

`rks evaluate claims` uses token-set Jaccard similarity with a default threshold
of 0.3. It computes a maximum-cardinality, one-to-one matching among pairs that
meet the threshold. Each extracted claim and reference claim contributes to at
most one match. Candidate traversal prefers higher similarity and stable index
tie breaks; it does not promise a globally maximal sum of similarities.

- Precision is matched pair count divided by extracted claim count.
- Recall is matched pair count divided by reference claim count.
- F1 is the harmonic mean of precision and recall.
- Empty denominators produce zero; empty claims do not match one another.

The response identifies `matching_policy` as
`one-to-one-max-cardinality-v1`, reports `true_positives`, and includes the
assigned `actual_index` for each matched reference. Unmatched references have
null `best_match` and `actual_index`, zero score, and `matched: false`.

Previously one extracted claim could count several times. With actual text
`alpha beta gamma` and references `alpha beta` and `alpha gamma`, the corrected
result is precision 1.0, recall 0.5, and F1 0.6667. The previous implementation
reported precision 2.0 and F1 1.3333. Scores now follow valid matches, not clamping.

Lexical overlap can still match opposite or numerically different statements.
These scores do not establish entailment, source fidelity, correct units, or
scientific validity. A compound claim can cover several propositions, but this
metric credits one match; split reference claims consistently and review
compound statements separately.

## Two different regression checks

Each JSON file in `tests/golden/` defines both thresholds:

```json
{
  "paper_fixture": "example",
  "min_f1": 0.75,
  "heuristic_min_f1": 0.25,
  "claims": ["One expected atomic claim."]
}
```

The prepared-import path ingests fixture text, imports predefined agent claims,
and scores the persisted records through the CLI. Its `min_f1` protects import,
storage, and evaluation behavior. It does not execute an agent.

The heuristic path imports fixture text, runs `extract_claims_for_paper`, and
scores the resulting persisted claims through the CLI. Its
`heuristic_min_f1` protects the deterministic extraction baseline. The public
extraction CLI offers agent/API modes, so this test calls the heuristic library
function directly. It does not validate PDF decoding or live model extraction.

| Fixture | Prepared-import gate | Heuristic gate | Scope |
| --- | --- | --- | --- |
| sample_transformer_paper | 0.5 | 0.65 | Synthetic source text |
| globocan_2020 | 0.75 | 0.25 | GLOBOCAN excerpt and 13 reference claims |

The heuristic gates preserve small-fixture regression baselines. A 0.25 gate is
not an acceptable scientific-release quality target. The source excerpts do
not contain every fact in the larger reference sets; expand and review
source/reference alignment before interpreting recall as full-paper extraction
quality. Prepared-import gates remain unchanged after the matching correction.

## Running the checks

Install the declared test dependency and run the full suite:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

For scoring and fixture checks alone:

```bash
python -m pytest tests/test_claim_evaluation.py tests/test_claim_quality_regression.py -v
```

CI uses pytest on Windows and Linux with Python 3.12–3.15. The earlier unittest
discovery command did not collect pytest-style tests already in this repository.
Package validation and installed-wheel smoke checks follow the test jobs.

To score claims stored for a paper, supply a JSON array of reference strings
(the CLI reference format differs from the regression fixture metadata):

```bash
rks evaluate claims <paper_id> --golden reference-claims.json --min-f1 0.5
```

## Adding evidence and live evaluations

Add a rights-cleared source excerpt, independently reviewed reference claims,
and a matching fixture entry. Record provenance and ensure every expected claim
is supported by the supplied source. Missing fixture registrations fail the
suite. Measure both paths, inspect mismatches, and set justified regression
thresholds. Do not lower thresholds to hide regressions.

Evaluate live agents and API models in a separate, explicit evaluation run.
Record input hashes, model/provider versions, prompts, outputs, extraction mode,
cost, and latency. Use held-out questions and human review of citation accuracy,
negation, numerical claims, and qualifications. Prepared-import and heuristic
test results must not be reported as live model scores.
