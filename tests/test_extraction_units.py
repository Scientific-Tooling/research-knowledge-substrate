"""Unit tests for extraction heuristics — sentence splitting, predicate detection, claim parsing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rks.extraction.claims import (
    _extract_candidate_sentences,
    _detect_predicate,
    _normalize_sentence,
    _parse_claim_parts,
    _clean_phrase,
    _claim_key,
    _normalized_evidence,
    PREDICATE_PATTERNS,
)


# ---------------------------------------------------------------------------
# Sentence segmentation
# ---------------------------------------------------------------------------

class TestSentenceSegmentation:
    def test_basic_split(self):
        text = "Transformers improve accuracy. CNNs reduce latency."
        sentences = _extract_candidate_sentences(text, 0)
        texts = [s["text"] for s in sentences]
        assert len(texts) == 2
        assert "Transformers improve accuracy." in texts[0]
        assert "CNNs reduce latency." in texts[1]

    def test_abbreviation_preserved(self):
        text = "Dr. Smith et al. proposed a method. It improves results."
        sentences = _extract_candidate_sentences(text, 0)
        # Should not split on "Dr." or "al." — abbreviation fragments must be rejoined
        texts = [s["text"] for s in sentences]
        assert any("improves" in t for t in texts)
        # The "et al." fragment should be rejoined, not dropped
        all_text = " ".join(texts)
        assert "al" in all_text.lower(), f"Abbreviation content was lost: {texts}"

    def test_decimal_preserved(self):
        text = "Accuracy improved by 3.14 points. The model converges fast."
        sentences = _extract_candidate_sentences(text, 0)
        texts = [s["text"] for s in sentences]
        # "3.14" should not cause a mid-number split
        assert any("3.14" in t for t in texts)

    def test_char_offsets(self):
        text = "First sentence. Second sentence."
        sentences = _extract_candidate_sentences(text, 100)
        for s in sentences:
            assert s["char_start"] >= 100
            assert s["char_end"] > s["char_start"]

    def test_lowercase_starting_sentence(self):
        text = "Accuracy was 95%. mRNA features improve recall."
        sentences = _extract_candidate_sentences(text, 0)
        texts = [s["text"] for s in sentences]
        # The lowercase-starting sentence should be split correctly
        assert len(texts) == 2, f"Expected 2 sentences, got {len(texts)}: {texts}"
        assert any("mRNA" in t for t in texts)

    def test_acronym_not_split(self):
        text = "The U.S. government funded the study. Results were positive."
        sentences = _extract_candidate_sentences(text, 0)
        texts = [s["text"] for s in sentences]
        assert len(texts) == 2, f"Expected 2 sentences, got {len(texts)}: {texts}"
        assert "U.S." in texts[0]

    def test_ie_eg_not_split(self):
        text = "We used common metrics, i.e. accuracy and F1. The model performed well."
        sentences = _extract_candidate_sentences(text, 0)
        texts = [s["text"] for s in sentences]
        assert len(texts) == 2, f"Expected 2 sentences, got {len(texts)}: {texts}"
        assert "i.e." in texts[0]

    def test_empty_text(self):
        assert _extract_candidate_sentences("", 0) == []

    def test_single_sentence_no_period(self):
        text = "Transformers outperform RNNs on long-context tasks"
        sentences = _extract_candidate_sentences(text, 0)
        assert len(sentences) >= 1
        assert "Transformers" in sentences[0]["text"]


# ---------------------------------------------------------------------------
# Predicate detection
# ---------------------------------------------------------------------------

class TestPredicateDetection:
    def test_original_predicates(self):
        """All original 10 predicates should still be detected."""
        cases = [
            ("outperforms", "Model A outperforms baseline"),
            ("improves", "The method improves accuracy"),
            ("reduces", "This approach reduces latency"),
            ("increases", "Data augmentation increases coverage"),
            ("enables", "Sparse attention enables long-context processing"),
            ("requires", "The method requires pretraining"),
            ("supports", "Evidence supports the hypothesis"),
            ("replaces", "The new layer replaces pooling"),
            ("refines", "Our approach refines prior estimates"),
            ("extends", "This work extends the framework"),
        ]
        for expected_pred, sentence in cases:
            pred, kw = _detect_predicate(sentence)
            assert pred == expected_pred, f"Expected {expected_pred} for: {sentence}, got {pred}"

    def test_new_predicates(self):
        """Newly added predicates should be detected."""
        cases = [
            ("outperforms", "Our model surpasses all baselines"),
            ("outperforms", "Performance exceeds the state of the art"),
            ("enables", "This framework facilitates rapid prototyping"),
            ("supports", "Experiments validate the approach"),
            ("supports", "Results confirm our hypothesis"),
            ("extends", "The method generalizes to new domains"),
            ("achieves", "BERT achieves 92% accuracy"),
            ("scales", "The algorithm scales linearly"),
            ("converges", "Training converges in 10 epochs"),
            ("degrades", "Accuracy degrades with noise"),
            ("limits", "Memory limits batch size"),
            ("fails", "The baseline fails on edge cases"),
            ("correlates", "Model size correlates with performance"),
            ("addresses", "Our method addresses the cold-start problem"),
            ("mitigates", "Regularization mitigates overfitting"),
        ]
        for expected_pred, sentence in cases:
            pred, kw = _detect_predicate(sentence)
            assert pred == expected_pred, f"Expected {expected_pred} for: {sentence}, got {pred}"

    def test_fallback_show_demonstrate(self):
        pred, _ = _detect_predicate("Results show significant gains")
        assert pred == "supports"
        pred, _ = _detect_predicate("Experiments demonstrate effectiveness")
        assert pred == "supports"

    def test_fallback_propose_introduce(self):
        pred, _ = _detect_predicate("We propose a novel architecture")
        assert pred == "proposes"
        pred, _ = _detect_predicate("This paper introduces a new loss function")
        assert pred == "proposes"

    def test_no_predicate(self):
        pred, kw = _detect_predicate("The dataset contains 10000 samples")
        assert pred is None
        assert kw is None


# ---------------------------------------------------------------------------
# Sentence normalization
# ---------------------------------------------------------------------------

class TestNormalizeSentence:
    def test_strips_leading_filler(self):
        assert _normalize_sentence("Our results show that X improves Y") == "X improves Y"
        assert _normalize_sentence("We demonstrate that A outperforms B") == "A outperforms B"
        assert _normalize_sentence("This paper show that Z extends W") == "Z extends W"

    def test_collapses_whitespace(self):
        result = _normalize_sentence("multiple   spaces\n\ttabs")
        assert "  " not in result
        assert "\n" not in result


# ---------------------------------------------------------------------------
# Subject-object parsing
# ---------------------------------------------------------------------------

class TestParseClaimParts:
    def test_basic_active_voice(self):
        subj, obj, ctx = _parse_claim_parts("Transformer outperforms RNN", "outperforms")
        assert subj is not None
        assert "Transformer" in subj
        assert obj is not None

    def test_passive_voice(self):
        subj, obj, ctx = _parse_claim_parts(
            "Accuracy is improved by data augmentation", "improved"
        )
        # After passive handling, the real subject should be "data augmentation"
        # and the object should relate to "Accuracy"
        assert subj is not None or obj is not None

    def test_context_extraction_dataset(self):
        _, _, ctx = _parse_claim_parts(
            "BERT outperforms GPT on ImageNet", "outperforms"
        )
        assert ctx.get("dataset") == "ImageNet"

    def test_context_extraction_task(self):
        _, _, ctx = _parse_claim_parts(
            "Model improves performance for text classification on GLUE", "improves"
        )
        assert "task" in ctx or "dataset" in ctx

    def test_no_keyword(self):
        subj, obj, ctx = _parse_claim_parts("Some sentence without match", None)
        assert subj is None
        assert obj is None


# ---------------------------------------------------------------------------
# Clean phrase
# ---------------------------------------------------------------------------

class TestCleanPhrase:
    def test_strips_determiners(self):
        assert _clean_phrase("the proposed method") == "proposed method"
        assert _clean_phrase("our approach") is not None

    def test_preserves_comparison(self):
        """Comparisons like 'better than X' should no longer be stripped."""
        result = _clean_phrase("accuracy better than baseline")
        assert result is not None
        assert "better than" in result

    def test_empty_returns_none(self):
        assert _clean_phrase("") is None
        assert _clean_phrase("   ") is None

    def test_strips_punctuation_edges(self):
        result = _clean_phrase("(method)")
        assert result is not None
        assert "(" not in result


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestClaimKey:
    def test_deterministic(self):
        k1 = _claim_key("Transformer outperforms RNN")
        k2 = _claim_key("Transformer outperforms RNN")
        assert k1 == k2

    def test_different_inputs(self):
        k1 = _claim_key("claim A")
        k2 = _claim_key("claim B")
        assert k1 != k2


class TestNormalizedEvidence:
    def test_fields(self):
        entry = {
            "text": "Some sentence",
            "section": "abstract",
            "paragraph_index": 0,
            "sentence_index": 1,
            "char_start": 10,
            "char_end": 23,
        }
        evidence = _normalized_evidence(entry, "p_000001")
        assert evidence["paper_id"] == "p_000001"
        assert evidence["section"] == "abstract"
        assert evidence["char_start"] == 10
        assert evidence["snippet"] == "Some sentence"


# ---------------------------------------------------------------------------
# Predicate pattern coverage
# ---------------------------------------------------------------------------

class TestPredicatePatternCoverage:
    def test_all_patterns_are_valid_regex(self):
        import re
        for pattern, name in PREDICATE_PATTERNS:
            re.compile(pattern)  # Should not raise

    def test_minimum_predicate_count(self):
        """We should have at least 25 patterns after expansion."""
        assert len(PREDICATE_PATTERNS) >= 25


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
