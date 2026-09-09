# Author: Maharshi Soni | License: MIT
"""Tests for core.nlp_engine module."""

import pytest

from core.nlp_engine import (
    classify_error,
    compute_similarity,
    extract_keywords,
    find_most_similar,
)


class TestClassifyError:
    """Tests for classify_error."""

    def test_locator_not_found(self):
        result = classify_error("Locator not found: css=#missing-element")
        assert result["category"] == "locator_not_found"
        assert result["confidence"] >= 0.9

    def test_text_mismatch(self):
        result = classify_error("Text mismatch: expected 'Hello' got 'Goodbye'")
        assert result["category"] == "text_mismatch"
        assert result["confidence"] >= 0.85

    def test_timeout(self):
        result = classify_error("Operation timed out after 30000ms")
        assert result["category"] == "timeout"
        assert result["confidence"] >= 0.9

    def test_network_error(self):
        result = classify_error("Network connection refused to host")
        assert result["category"] == "network_error"
        assert result["confidence"] >= 0.85

    def test_unknown(self):
        result = classify_error("Something completely bizarre occurred overnight")
        assert result["category"] == "unknown"
        assert result["confidence"] < 0.5

    def test_multiple_keywords_increase_confidence(self):
        result = classify_error("Locator not found: selector for element not found")
        assert result["category"] == "locator_not_found"
        # Multiple keyword hits should boost confidence
        assert result["confidence"] >= 0.95

    def test_result_has_keywords(self):
        result = classify_error("Locator not found")
        assert "keywords" in result
        assert isinstance(result["keywords"], list)


class TestComputeSimilarity:
    """Tests for compute_similarity (uses TF-IDF fallback)."""

    def test_identical_texts(self):
        score = compute_similarity("hello world", "hello world")
        assert score >= 0.99

    def test_similar_texts(self):
        score = compute_similarity(
            "the element selector was not found on the page",
            "a CSS selector could not be found in the DOM",
        )
        assert score > 0.0

    def test_dissimilar_texts(self):
        score = compute_similarity(
            "network connection error",
            "the sky is blue and grass is green",
        )
        # These are quite different
        assert score < 0.5

    def test_empty_text(self):
        score = compute_similarity("", "")
        # Both empty should yield 0 (no tokens)
        assert score == 0.0

    def test_returns_float(self):
        score = compute_similarity("test one", "test two")
        assert isinstance(score, float)


class TestFindMostSimilar:
    """Tests for find_most_similar."""

    def test_top_k(self):
        candidates = [
            "locator not found error",
            "network timeout",
            "CSS selector failed",
            "text assertion mismatch",
        ]
        results = find_most_similar("selector not found", candidates, top_k=2)
        assert len(results) == 2
        # Each result is (candidate, score) tuple
        assert isinstance(results[0][0], str)
        assert isinstance(results[0][1], float)

    def test_sorted_by_score(self):
        candidates = ["apple", "banana", "cherry"]
        results = find_most_similar("apple", candidates, top_k=3)
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_candidates(self):
        results = find_most_similar("query", [], top_k=3)
        assert results == []

    def test_top_match_is_relevant(self):
        candidates = [
            "Locator not found: the CSS selector failed to resolve",
            "The database connection was lost during the query",
            "User authentication token expired after timeout",
        ]
        results = find_most_similar("CSS selector was not found", candidates, top_k=1)
        assert len(results) == 1
        # The locator-related candidate should be the best match
        assert "selector" in results[0][0].lower() or "locator" in results[0][0].lower()


class TestExtractKeywords:
    """Tests for extract_keywords."""

    def test_basic_extraction(self):
        text = "The locator was not found because the CSS selector changed"
        keywords = extract_keywords(text, top_k=3)
        assert isinstance(keywords, list)
        assert len(keywords) <= 3

    def test_filters_stop_words(self):
        text = "the is a an and but or not to of in for on with"
        keywords = extract_keywords(text, top_k=5)
        # All are stop words or too short, so should get few/no results
        assert len(keywords) == 0

    def test_returns_frequent_tokens(self):
        text = "error error error timeout timeout success"
        keywords = extract_keywords(text, top_k=2)
        assert "error" in keywords

    def test_empty_text(self):
        keywords = extract_keywords("", top_k=5)
        assert keywords == []
