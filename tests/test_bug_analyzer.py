# Author: Maharshi Soni | License: MIT
"""Tests for core.bug_analyzer module."""

import pytest

from core.state import AgentState, Locator, TestCase, TestStep, TestStatus
from core.bug_analyzer import analyze_bugs


def _make_failed_state() -> AgentState:
    """Create a state with a failed locator test case."""
    state = AgentState()
    tc = TestCase(
        test_id="TC-FAIL01",
        name="Login Test",
        tags=["smoke", "auth", "critical"],
        steps=[
            TestStep(
                action="click",
                locator=Locator("css", ".missing-btn"),
                status=TestStatus.FAILED,
                error_message="Locator not found: css=.missing-btn",
            ),
        ],
        status=TestStatus.FAILED,
        error_summary="Locator not found: css=.missing-btn",
    )
    state.test_cases = [tc]
    state.failed_steps = [
        {
            "test_id": "TC-FAIL01",
            "test_name": "Login Test",
            "step_index": 0,
            "action": "click",
            "locator": {"strategy": "css", "value": ".missing-btn"},
            "error_message": "Locator not found: css=.missing-btn",
            "is_locator_failure": True,
        }
    ]
    return state


def _make_text_mismatch_state() -> AgentState:
    """Create a state with a text mismatch failure."""
    state = AgentState()
    tc = TestCase(
        test_id="TC-TXT01",
        name="Text Assert Test",
        tags=["functional"],
        steps=[
            TestStep(
                action="assert_text",
                locator=Locator("css", ".heading"),
                value="Expected",
                status=TestStatus.FAILED,
                error_message="Text mismatch: expected 'Expected', got 'Actual'",
            ),
        ],
        status=TestStatus.FAILED,
        error_summary="Text mismatch: expected 'Expected', got 'Actual'",
    )
    state.test_cases = [tc]
    state.failed_steps = [
        {
            "test_id": "TC-TXT01",
            "test_name": "Text Assert Test",
            "step_index": 0,
            "action": "assert_text",
            "locator": {"strategy": "css", "value": ".heading"},
            "error_message": "Text mismatch: expected 'Expected', got 'Actual'",
            "is_locator_failure": False,
        }
    ]
    return state


class TestAnalyzeBugs:
    """Tests for the analyze_bugs node function."""

    def test_no_failures(self):
        state = AgentState()
        result = analyze_bugs(state)
        assert result.should_heal is False

    def test_locator_failure_is_healable(self):
        state = _make_failed_state()
        result = analyze_bugs(state)
        assert result.should_heal is True
        tc = result.test_cases[0]
        assert tc.bug_analysis is not None
        assert tc.bug_analysis["category"] == "locator_not_found"
        assert tc.bug_analysis["healable"] is True

    def test_text_mismatch_not_healable(self):
        state = _make_text_mismatch_state()
        result = analyze_bugs(state)
        assert result.should_heal is False
        tc = result.test_cases[0]
        assert tc.bug_analysis is not None
        assert tc.bug_analysis["category"] == "text_mismatch"
        assert tc.bug_analysis["healable"] is False

    def test_severity_elevation_for_critical_tag(self):
        state = _make_failed_state()
        result = analyze_bugs(state)
        tc = result.test_cases[0]
        # locator_not_found base is "major", but "critical" tag elevates it
        assert tc.bug_analysis["severity"] == "critical"

    def test_severity_for_non_critical_tag(self):
        state = _make_text_mismatch_state()
        result = analyze_bugs(state)
        tc = result.test_cases[0]
        # text_mismatch base is "minor", no critical tag
        assert tc.bug_analysis["severity"] == "minor"

    def test_analysis_has_required_fields(self):
        state = _make_failed_state()
        result = analyze_bugs(state)
        analysis = result.test_cases[0].bug_analysis
        required_fields = [
            "category",
            "classification_confidence",
            "severity",
            "keywords",
            "root_cause_hypothesis",
            "pattern_similarity",
            "healable",
        ]
        for field in required_fields:
            assert field in analysis, f"Missing field: {field}"

    def test_root_cause_hypothesis_is_string(self):
        state = _make_failed_state()
        result = analyze_bugs(state)
        hypothesis = result.test_cases[0].bug_analysis["root_cause_hypothesis"]
        assert isinstance(hypothesis, str)
        assert len(hypothesis) > 0

    def test_pattern_similarity_is_float(self):
        state = _make_failed_state()
        result = analyze_bugs(state)
        sim = result.test_cases[0].bug_analysis["pattern_similarity"]
        assert isinstance(sim, float)
        assert 0.0 <= sim <= 1.0
