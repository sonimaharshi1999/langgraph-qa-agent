# Author: Maharshi Soni | License: MIT
"""Tests for core.state module."""

import pytest

from core.state import (
    AgentState,
    Locator,
    NodeName,
    TestCase,
    TestStatus,
    TestStep,
)


class TestLocator:
    """Tests for the Locator dataclass."""

    def test_create_locator(self):
        loc = Locator(strategy="css", value="#my-id", description="My element")
        assert loc.strategy == "css"
        assert loc.value == "#my-id"
        assert loc.description == "My element"
        assert loc.confidence == 1.0

    def test_to_dict(self):
        loc = Locator("xpath", "//div", "A div", confidence=0.8)
        d = loc.to_dict()
        assert d == {
            "strategy": "xpath",
            "value": "//div",
            "description": "A div",
            "confidence": 0.8,
        }

    def test_from_dict(self):
        data = {
            "strategy": "css",
            "value": ".btn",
            "description": "Button",
            "confidence": 0.95,
        }
        loc = Locator.from_dict(data)
        assert loc.strategy == "css"
        assert loc.value == ".btn"
        assert loc.confidence == 0.95

    def test_from_dict_defaults(self):
        data = {"strategy": "id", "value": "main"}
        loc = Locator.from_dict(data)
        assert loc.description == ""
        assert loc.confidence == 1.0


class TestTestStep:
    """Tests for the TestStep dataclass."""

    def test_create_step(self):
        step = TestStep(action="click", description="Click button")
        assert step.action == "click"
        assert step.status == TestStatus.SKIPPED
        assert step.locator is None

    def test_step_with_locator(self):
        loc = Locator("css", "#btn")
        step = TestStep(action="click", locator=loc, description="Click")
        d = step.to_dict()
        assert d["locator"]["value"] == "#btn"
        assert d["action"] == "click"

    def test_step_roundtrip(self):
        loc = Locator("css", ".item", "Item", 0.9)
        step = TestStep(
            action="type",
            locator=loc,
            value="hello",
            description="Type text",
            status=TestStatus.PASSED,
            duration_ms=15.5,
        )
        d = step.to_dict()
        restored = TestStep.from_dict(d)
        assert restored.action == "type"
        assert restored.value == "hello"
        assert restored.status == TestStatus.PASSED
        assert restored.locator.value == ".item"
        assert restored.duration_ms == 15.5

    def test_step_from_dict_minimal(self):
        data = {"action": "navigate"}
        step = TestStep.from_dict(data)
        assert step.action == "navigate"
        assert step.locator is None
        assert step.status == TestStatus.SKIPPED


class TestTestCase:
    """Tests for the TestCase dataclass."""

    def test_auto_id(self):
        tc = TestCase(name="My Test")
        assert tc.test_id.startswith("TC-")
        assert len(tc.test_id) == 11  # "TC-" + 8 hex chars

    def test_explicit_id(self):
        tc = TestCase(test_id="TC-CUSTOM01", name="Custom")
        assert tc.test_id == "TC-CUSTOM01"

    def test_to_dict(self):
        step = TestStep(action="navigate", value="/home", description="Go home")
        tc = TestCase(
            test_id="TC-001",
            name="Nav Test",
            description="Test navigation",
            tags=["smoke"],
            steps=[step],
            status=TestStatus.PASSED,
        )
        d = tc.to_dict()
        assert d["test_id"] == "TC-001"
        assert d["name"] == "Nav Test"
        assert d["tags"] == ["smoke"]
        assert len(d["steps"]) == 1
        assert d["status"] == "passed"

    def test_roundtrip(self):
        step = TestStep(action="click", description="Click")
        tc = TestCase(
            test_id="TC-RT",
            name="Roundtrip",
            tags=["functional"],
            steps=[step],
            status=TestStatus.FAILED,
            error_summary="Something broke",
        )
        d = tc.to_dict()
        restored = TestCase.from_dict(d)
        assert restored.test_id == "TC-RT"
        assert restored.status == TestStatus.FAILED
        assert restored.error_summary == "Something broke"
        assert len(restored.steps) == 1


class TestAgentState:
    """Tests for the AgentState dataclass."""

    def test_defaults(self):
        state = AgentState()
        assert state.target_url == "https://example.com"
        assert state.run_id.startswith("RUN-")
        assert state.started_at != ""
        assert state.current_node == NodeName.TEST_PLANNER
        assert state.test_cases == []

    def test_custom_state(self):
        state = AgentState(
            target_url="https://myapp.com",
            test_suite_name="My Suite",
            config={"key": "value"},
        )
        assert state.target_url == "https://myapp.com"
        assert state.test_suite_name == "My Suite"
        assert state.config["key"] == "value"

    def test_to_dict(self):
        state = AgentState(target_url="https://test.com")
        d = state.to_dict()
        assert d["target_url"] == "https://test.com"
        assert d["current_node"] == "test_planner"
        assert isinstance(d["test_cases"], list)
        assert isinstance(d["errors"], list)


class TestEnums:
    """Tests for enum definitions."""

    def test_test_status_values(self):
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.ERROR.value == "error"
        assert TestStatus.SKIPPED.value == "skipped"
        assert TestStatus.HEALED.value == "healed"

    def test_node_name_values(self):
        assert NodeName.TEST_PLANNER.value == "test_planner"
        assert NodeName.TEST_EXECUTOR.value == "test_executor"
        assert NodeName.BUG_ANALYZER.value == "bug_analyzer"
        assert NodeName.SELF_HEALER.value == "self_healer"
        assert NodeName.REPORTER.value == "reporter"
        assert NodeName.END.value == "__end__"
