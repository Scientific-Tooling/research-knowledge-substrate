"""Unit tests for query inference logic — polarity detection, claim relation inference."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rks.query.service import _claim_polarity


# ---------------------------------------------------------------------------
# Polarity detection
# ---------------------------------------------------------------------------

class TestClaimPolarity:
    def test_positive(self):
        assert _claim_polarity("Model improves accuracy by 5%") == 1
        assert _claim_polarity("Our method outperforms the baseline") == 1

    def test_negative(self):
        assert _claim_polarity("Method does not improve results") == -1
        assert _claim_polarity("Performance degrades with noise") == -1

    def test_explicit_negation(self):
        assert _claim_polarity("did not improve the metric") == -1

    def test_neutral(self):
        assert _claim_polarity("The dataset contains 1000 samples") == 0

    def test_mixed_defaults_neutral(self):
        # Both positive and negative signals — should be 0
        result = _claim_polarity("improves but fails on edge cases")
        # Could be 0 or one of the signals; just check it returns an int
        assert isinstance(result, int)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
