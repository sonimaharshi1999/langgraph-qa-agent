# Author: Maharshi Soni | License: MIT
"""Tests for core.self_healer module."""

import pytest

from core.state import AgentState, Locator, TestCase, TestStep, TestStatus
from core.self_healer import (
    _try_alternative_lookup,
    _try_attribute_relaxation,
    _try_strategy_switch,
    heal_and_retry,
    heal_locator,
)


class TestTryAlternativeLookup:
    """Tests for _try_alternative_lookup."""

    def test_known_alternative(self):
        loc = Locator("css", ".welcome-message", "Welcome banner")
        result = _try_alternative_lookup(loc)
        assert result is not None
        assert result.value == ".user-greeting"
        assert result.confidence < 1.0

    def test_no_alternative(self):
        loc = Locator("css", ".totally-unknown", "Unknown element")
        result = _try_alternative_lookup(loc)
        assert result is None

    def test_xpath_alternative(self):
        loc = Locator("xpath", "//div[contains(@class, 'sidebar')]", "Sidebar")
        result = _try_alternative_lookup(loc)
        assert result is not None
        assert result.value == "aside.sidebar-panel"


class TestTryAttributeRelaxation:
    """Tests for _try_attribute_relaxation."""

    def test_non_css_returns_none(self):
        loc = Locator("xpath", "//div", "A div")
        result = _try_attribute_relaxation(loc)
        assert result is None

    def test_no_relaxation_possible(self):
        loc = Locator("css", ".simple-class", "Simple")
        result = _try_attribute_relaxation(loc)
        # .simple-class is not in _KNOWN_SELECTORS, and relaxing it doesn't help
        assert result is None

    def test_relaxation_unchanged_returns_none(self):
        # A selector with nothing to relax
        loc = Locator("css", "#login-form", "Login form")
        result = _try_attribute_relaxation(loc)
        # #login-form unchanged, but since it IS in _KNOWN_SELECTORS
        # the relaxation check sees relaxed == value and returns None
        assert result is None


class TestTryStrategySwitch:
    """Tests for _try_strategy_switch."""

    def test_css_id_to_xpath(self):
        loc = Locator("css", "#myid", "An element")
        result = _try_strategy_switch(loc)
        assert result is not None
        assert result.strategy == "xpath"
        assert "@id='myid'" in result.value

    def test_css_class_to_xpath(self):
        loc = Locator("css", ".myclass", "An element")
        result = _try_strategy_switch(loc)
        assert result is not None
        assert result.strategy == "xpath"
        assert "contains(@class, 'myclass')" in result.value

    def test_complex_css_not_converted(self):
        loc = Locator("css", "div.class > span.inner", "Complex")
        result = _try_strategy_switch(loc)
        # Complex selectors are not handled by the simple converter
        assert result is None


class TestHealLocator:
    """Tests for heal_locator (combined strategies)."""

    def test_heal_known_alternative(self):
        loc = Locator("css", ".welcome-message")
        result = heal_locator(loc)
        assert result is not None
        assert result.value == ".user-greeting"

    def test_heal_xpath_sidebar(self):
        loc = Locator("xpath", "//div[contains(@class, 'sidebar')]")
        result = heal_locator(loc)
        assert result is not None
        assert result.value == "aside.sidebar-panel"

    def test_heal_impossible(self):
        loc = Locator("css", "div.very-specific > span.nested:nth-child(3)")
        result = heal_locator(loc)
        # None of the strategies can fix this
        assert result is None

    def test_heal_returns_locator_type(self):
        loc = Locator("css", ".welcome-message")
        result = heal_locator(loc)
        assert isinstance(result, Locator)


class TestHealAndRetry:
    """Tests for the heal_and_retry node function."""

    def test_no_healing_needed(self):
        state = AgentState()
        state.should_heal = False
        result = heal_and_retry(state)
        assert len(result.healed_locators) == 0

    def test_heal_locator_failure(self):
        state = AgentState()
        tc = TestCase(
            test_id="TC-HEAL01",
            name="Healable Test",
            steps=[
                TestStep(action="navigate", value="https://example.com"),
                TestStep(
                    action="assert_visible",
                    locator=Locator("css", ".welcome-message"),
                    status=TestStatus.FAILED,
                    error_message="Locator not found: css=.welcome-message",
                ),
            ],
            status=TestStatus.FAILED,
        )
        state.test_cases = [tc]
        state.should_heal = True
        state.failed_steps = [
            {
                "test_id": "TC-HEAL01",
                "test_name": "Healable Test",
                "step_index": 1,
                "action": "assert_visible",
                "locator": {"strategy": "css", "value": ".welcome-message"},
                "error_message": "Locator not found: css=.welcome-message",
                "is_locator_failure": True,
            }
        ]

        result = heal_and_retry(state)
        assert len(result.healed_locators) == 1
        assert result.healed_locators[0]["healed"]["value"] == ".user-greeting"
        assert result.should_heal is False

    def test_heal_updates_test_status(self):
        state = AgentState()
        tc = TestCase(
            test_id="TC-HEAL02",
            name="Heal And Pass",
            steps=[
                TestStep(
                    action="navigate",
                    value="https://example.com",
                    status=TestStatus.PASSED,
                ),
                TestStep(
                    action="assert_text",
                    locator=Locator("css", ".welcome-message"),
                    value="Welcome, Test User",
                    status=TestStatus.FAILED,
                    error_message="Locator not found: css=.welcome-message",
                ),
            ],
            status=TestStatus.FAILED,
        )
        state.test_cases = [tc]
        state.should_heal = True
        state.failed_steps = [
            {
                "test_id": "TC-HEAL02",
                "test_name": "Heal And Pass",
                "step_index": 1,
                "action": "assert_text",
                "locator": {"strategy": "css", "value": ".welcome-message"},
                "error_message": "Locator not found: css=.welcome-message",
                "is_locator_failure": True,
            }
        ]

        result = heal_and_retry(state)
        tc = result.test_cases[0]
        # The healed locator .user-greeting returns "Welcome, Test User"
        assert tc.status == TestStatus.HEALED
        assert tc.retry_count == 1

    def test_non_locator_failures_skipped(self):
        state = AgentState()
        tc = TestCase(
            test_id="TC-NLF",
            name="Non Locator Fail",
            steps=[
                TestStep(
                    action="assert_text",
                    locator=Locator("css", "h1.page-title"),
                    value="Wrong",
                    status=TestStatus.FAILED,
                    error_message="Text mismatch",
                ),
            ],
            status=TestStatus.FAILED,
        )
        state.test_cases = [tc]
        state.should_heal = True
        state.failed_steps = [
            {
                "test_id": "TC-NLF",
                "step_index": 0,
                "action": "assert_text",
                "locator": {"strategy": "css", "value": "h1.page-title"},
                "error_message": "Text mismatch",
                "is_locator_failure": False,
            }
        ]

        result = heal_and_retry(state)
        assert len(result.healed_locators) == 0
