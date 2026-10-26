from __future__ import annotations

import itertools
import unittest

from rks.cli._context import _evaluate_claims_against_golden


class ClaimEvaluationTest(unittest.TestCase):
    def test_one_combined_claim_cannot_match_two_references(self) -> None:
        result = _evaluate_claims_against_golden(["alpha beta gamma"], ["alpha beta", "alpha gamma"])
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["f1"], 0.6667)
        self.assertEqual(sum(pair["matched"] for pair in result["matched_pairs"]), 1)

    def test_duplicate_predictions_reduce_precision(self) -> None:
        result = _evaluate_claims_against_golden(["alpha beta", "alpha beta"], ["alpha beta"])
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 1.0)

    def test_reassignment_finds_all_compatible_matches(self) -> None:
        # A greedy match uses 'alpha beta' for 'alpha', leaving the exact
        # reference unmatched. Reassignment must recover both valid pairs.
        for actual in itertools.permutations(["alpha beta", "alpha gamma"]):
            for golden in itertools.permutations(["alpha", "alpha beta"]):
                with self.subTest(actual=actual, golden=golden):
                    result = _evaluate_claims_against_golden(list(actual), list(golden), 0.5)
                    self.assertEqual(result["f1"], 1.0)
                    indices = [pair["actual_index"] for pair in result["matched_pairs"]]
                    self.assertEqual(len(set(indices)), 2)

    def test_empty_and_unmatched_inputs_have_zero_scores(self) -> None:
        for actual, golden in [([], []), ([], ["alpha"]), (["alpha"], []), (["alpha"], ["beta"]), ([""], [""])]:
            with self.subTest(actual=actual, golden=golden):
                result = _evaluate_claims_against_golden(actual, golden)
                self.assertEqual([result[key] for key in ("precision", "recall", "f1")], [0.0, 0.0, 0.0])

    def test_scores_are_bounded_with_overlapping_and_duplicate_claims(self) -> None:
        claims = ["alpha", "alpha beta", "alpha gamma", "alpha beta", "delta"]
        for actual_count in range(len(claims) + 1):
            for golden_count in range(len(claims) + 1):
                result = _evaluate_claims_against_golden(claims[:actual_count], claims[:golden_count])
                for key in ("precision", "recall", "f1"):
                    self.assertGreaterEqual(result[key], 0.0)
                    self.assertLessEqual(result[key], 1.0)

    def test_threshold_is_inclusive_and_results_are_deterministic(self) -> None:
        first = _evaluate_claims_against_golden(["alpha beta"], ["alpha"], 0.5)
        self.assertEqual(first["f1"], 1.0)
        self.assertEqual(first, _evaluate_claims_against_golden(["alpha beta"], ["alpha"], 0.5))
        self.assertEqual(_evaluate_claims_against_golden(["alpha beta"], ["alpha"], 0.51)["f1"], 0.0)

    def test_invalid_threshold_is_rejected(self) -> None:
        for threshold in [-1, 0, 1.1, float("nan")]:
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                _evaluate_claims_against_golden(["alpha"], ["alpha"], threshold)


if __name__ == "__main__":
    unittest.main()
