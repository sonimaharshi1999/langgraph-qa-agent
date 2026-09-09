# Author: Maharshi Soni | License: MIT
"""Tests for core.test_executor module."""

import pytest

from core.state import AgentState, Locator, TestCase, TestStep, TestStatus
from core.test_executor import (
    _dispatch_action,
    _execute_test_case,
    execute_tests,
)


class TestDispatchAction:
    """Tests for _dispatch_action."""

    def test_navigate_always_passes(self):
        step = TestStep(action="navigate", value="https://example.com")
        result = _dispatch_action(step)
        assert result.status == TestStatus.PASSED
        assert result.duration_ms > 0

    def test_click_known_selector(self):
        step = TestStep(
            action="click",
            locator=Locator("css", "button[type='submit']"),
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.PASSED

    def test_click_unknown_selector(self):
        step = TestStep(
            action="click",
            locator=Locator("css", ".does-not-exist"),
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.FAILED
        assert "Locator not found" in result.error_message

    def test_click_no_locator(self):
        step = TestStep(action="click")
        result = _dispatch_action(step)
        assert result.status == TestStatus.ERROR
        assert "No locator" in result.error_message

    def test_type_known_selector(self):
        step = TestStep(
            action="type",
            locator=Locator("css", "input[name='username']"),
            value="hello",
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.PASSED

    def test_assert_visible_known(self):
        step = TestStep(
            action="assert_visible",
            locator=Locator("css", "#login-form"),
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.PASSED

    def test_assert_visible_unknown(self):
        step = TestStep(
            action="assert_visible",
            locator=Locator("css", ".nonexistent"),
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.FAILED

    def test_assert_text_match(self):
        step = TestStep(
            action="assert_text",
            locator=Locator("css", "h1.page-title"),
            value="About Us",
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.PASSED

    def test_assert_text_mismatch(self):
        step = TestStep(
            action="assert_text",
            locator=Locator("css", "h1.page-title"),
            value="Wrong Text",
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.FAILED
        assert "Text mismatch" in result.error_message

    def test_assert_text_unknown_locator(self):
        step = TestStep(
            action="assert_text",
            locator=Locator("css", ".missing"),
            value="anything",
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.FAILED
        assert "Locator not found" in result.error_message

    def test_unknown_action(self):
        step = TestStep(action="hover", locator=Locator("css", "#btn"))
        result = _dispatch_action(step)
        assert result.status == TestStatus.ERROR
        assert "Unknown action" in result.error_message

    def test_uses_healed_locator(self):
        """When healed_locator is set, it should be used instead of the original."""
        step = TestStep(
            action="click",
            locator=Locator("css", ".missing"),
            healed_locator=Locator("css", "button[type='submit']"),
        )
        result = _dispatch_action(step)
        assert result.status == TestStatus.PASSED


class TestExecuteTestCase:
    """Tests for _execute_test_case."""

    def test_all_pass(self):
        tc = TestCase(
            name="Simple Nav",
            steps=[
                TestStep(action="navigate", value="https://example.com"),
                TestStep(action="assert_visible", locator=Locator("css", "#login-form")),
            ],
        )
        result = _execute_test_case(tc)
        assert result.status == TestStatus.PASSED
        assert result.duration_ms > 0

    def test_fail_fast(self):
        """Steps after a failure should be skipped."""
        tc = TestCase(
            name="Fail Fast",
            steps=[
                TestStep(action="navigate", value="https://example.com"),
                TestStep(action="click", locator=Locator("css", ".missing")),
                TestStep(action="navigate", value="https://example.com/after"),
            ],
        )
        result = _execute_test_case(tc)
        assert result.status == TestStatus.FAILED
        assert result.steps[0].status == TestStatus.PASSED
        assert result.steps[1].status == TestStatus.FAILED
        assert result.steps[2].status == TestStatus.SKIPPED

    def test_error_status(self):
        tc = TestCase(
            name="Error",
            steps=[TestStep(action="hover", locator=Locator("css", "#x"))],
        )
        result = _execute_test_case(tc)
        assert result.status == TestStatus.ERROR


class TestExecuteTests:
    """Tests for the execute_tests node function."""

    def test_populates_failed_steps(self):
        state = AgentState()
        state.test_cases = [
            TestCase(
                test_id="TC-PASS",
                name="Pass",
                steps=[TestStep(action="navigate", value="https://example.com")],
            ),
            TestCase(
                test_id="TC-FAIL",
                name="Fail",
                steps=[
                    TestStep(
                        action="click",
                        locator=Locator("css", ".nonexistent"),
                    )
                ],
            ),
        ]
        result = execute_tests(state)
        assert len(result.failed_steps) == 1
        assert result.failed_steps[0]["test_id"] == "TC-FAIL"
        assert result.failed_steps[0]["is_locator_failure"] is True

    def test_all_pass_no_failures(self):
        state = AgentState()
        state.test_cases = [
            TestCase(
                test_id="TC-OK",
                name="OK",
                steps=[TestStep(action="navigate", value="https://example.com")],
            ),
        ]
        result = execute_tests(state)
        assert len(result.failed_steps) == 0
