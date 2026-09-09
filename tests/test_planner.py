# Author: Maharshi Soni | License: MIT
"""Tests for core.test_planner module."""

import pytest

from core.state import AgentState, TestStatus
from core.test_planner import get_available_templates, plan_tests


class TestGetAvailableTemplates:
    """Tests for get_available_templates."""

    def test_returns_list(self):
        templates = get_available_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_expected_templates(self):
        templates = get_available_templates()
        assert "login_flow" in templates
        assert "search_flow" in templates
        assert "navigation_flow" in templates
        assert "form_validation" in templates
        assert "responsive_layout" in templates


class TestPlanTests:
    """Tests for the plan_tests node function."""

    def test_plan_all_templates(self):
        state = AgentState(target_url="https://example.com")
        result = plan_tests(state)
        assert len(result.test_cases) == 5
        assert result.current_test_index == 0

    def test_plan_specific_templates(self):
        state = AgentState(
            target_url="https://example.com",
            config={"templates": ["login_flow", "search_flow"]},
        )
        result = plan_tests(state)
        assert len(result.test_cases) == 2
        names = [tc.name for tc in result.test_cases]
        assert "User Login Flow" in names
        assert "Search Functionality" in names

    def test_plan_filter_by_tags(self):
        state = AgentState(
            target_url="https://example.com",
            config={"tags": ["smoke"]},
        )
        result = plan_tests(state)
        # login_flow and navigation_flow have the "smoke" tag
        assert len(result.test_cases) == 2
        for tc in result.test_cases:
            assert "smoke" in tc.tags

    def test_plan_empty_when_no_match(self):
        state = AgentState(
            target_url="https://example.com",
            config={"tags": ["nonexistent_tag"]},
        )
        result = plan_tests(state)
        assert len(result.test_cases) == 0

    def test_url_substitution(self):
        state = AgentState(target_url="https://myapp.com")
        result = plan_tests(state)
        # Check that navigate steps have the correct URL
        for tc in result.test_cases:
            for step in tc.steps:
                if step.action == "navigate" and step.value:
                    assert "https://myapp.com" in step.value

    def test_all_steps_start_skipped(self):
        state = AgentState(target_url="https://example.com")
        result = plan_tests(state)
        for tc in result.test_cases:
            for step in tc.steps:
                assert step.status == TestStatus.SKIPPED

    def test_test_ids_are_unique(self):
        state = AgentState(target_url="https://example.com")
        result = plan_tests(state)
        ids = [tc.test_id for tc in result.test_cases]
        assert len(ids) == len(set(ids))

    def test_test_cases_have_tags(self):
        state = AgentState(target_url="https://example.com")
        result = plan_tests(state)
        for tc in result.test_cases:
            assert len(tc.tags) > 0
