# Author: Maharshi Soni | License: MIT
"""Tests for core.reporter module."""

import json
import os
import tempfile

import pytest

from core.state import AgentState, Locator, TestCase, TestStep, TestStatus
from core.reporter import (
    _build_slack_message,
    _summarize_results,
    generate_report,
    report_results,
    save_report,
    send_slack_notification,
)


def _make_state_with_results() -> AgentState:
    """Create a state with a mix of passed and failed test cases."""
    state = AgentState(
        target_url="https://example.com",
        test_suite_name="Test Suite",
    )
    state.test_cases = [
        TestCase(
            test_id="TC-PASS01",
            name="Passing Test",
            tags=["smoke"],
            steps=[
                TestStep(
                    action="navigate",
                    value="https://example.com",
                    status=TestStatus.PASSED,
                    duration_ms=10.0,
                ),
            ],
            status=TestStatus.PASSED,
            duration_ms=10.0,
        ),
        TestCase(
            test_id="TC-FAIL01",
            name="Failing Test",
            tags=["functional"],
            steps=[
                TestStep(
                    action="click",
                    locator=Locator("css", ".missing"),
                    status=TestStatus.FAILED,
                    error_message="Locator not found",
                    duration_ms=5.0,
                ),
            ],
            status=TestStatus.FAILED,
            error_summary="Locator not found",
            bug_analysis={"category": "locator_not_found", "severity": "major"},
            duration_ms=5.0,
        ),
        TestCase(
            test_id="TC-HEAL01",
            name="Healed Test",
            tags=["smoke"],
            steps=[
                TestStep(
                    action="navigate",
                    value="https://example.com",
                    status=TestStatus.PASSED,
                    duration_ms=8.0,
                ),
            ],
            status=TestStatus.HEALED,
            duration_ms=8.0,
        ),
    ]
    state.healed_locators = [
        {
            "test_id": "TC-HEAL01",
            "step_index": 0,
            "original": {"strategy": "css", "value": ".old"},
            "healed": {"strategy": "css", "value": ".new"},
        }
    ]
    return state


class TestSummarizeResults:
    """Tests for _summarize_results."""

    def test_counts(self):
        state = _make_state_with_results()
        summary = _summarize_results(state)
        assert summary["total_tests"] == 3
        assert summary["counts"]["passed"] == 1
        assert summary["counts"]["failed"] == 1
        assert summary["counts"]["healed"] == 1
        assert summary["pass_rate"] == pytest.approx(66.7, abs=0.1)

    def test_duration(self):
        state = _make_state_with_results()
        summary = _summarize_results(state)
        assert summary["total_duration_ms"] == 23.0

    def test_healed_locators_count(self):
        state = _make_state_with_results()
        summary = _summarize_results(state)
        assert summary["healed_locators"] == 1

    def test_empty_state(self):
        state = AgentState()
        summary = _summarize_results(state)
        assert summary["total_tests"] == 0
        assert summary["pass_rate"] == 0.0


class TestGenerateReport:
    """Tests for generate_report."""

    def test_report_structure(self):
        state = _make_state_with_results()
        report = generate_report(state)
        assert "run_id" in report
        assert "suite_name" in report
        assert "target_url" in report
        assert "started_at" in report
        assert "completed_at" in report
        assert "summary" in report
        assert "test_cases" in report
        assert "healed_locators" in report
        assert "errors" in report

    def test_report_values(self):
        state = _make_state_with_results()
        report = generate_report(state)
        assert report["suite_name"] == "Test Suite"
        assert report["target_url"] == "https://example.com"
        assert len(report["test_cases"]) == 3

    def test_report_is_json_serializable(self):
        state = _make_state_with_results()
        report = generate_report(state)
        # Should not raise
        json_str = json.dumps(report)
        assert isinstance(json_str, str)


class TestSaveReport:
    """Tests for save_report."""

    def test_saves_file(self):
        state = _make_state_with_results()
        report = generate_report(state)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = save_report(report, output_dir=tmpdir)
            assert os.path.exists(filepath)
            assert filepath.endswith(".json")

    def test_file_content_is_valid_json(self):
        state = _make_state_with_results()
        report = generate_report(state)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = save_report(report, output_dir=tmpdir)
            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded["run_id"] == report["run_id"]

    def test_creates_directory(self):
        state = _make_state_with_results()
        report = generate_report(state)
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "nested", "dir")
            filepath = save_report(report, output_dir=nested)
            assert os.path.exists(filepath)


class TestBuildSlackMessage:
    """Tests for _build_slack_message."""

    def test_message_has_blocks(self):
        state = _make_state_with_results()
        report = generate_report(state)
        message = _build_slack_message(report)
        assert "blocks" in message
        assert len(message["blocks"]) > 0

    def test_header_block(self):
        state = _make_state_with_results()
        report = generate_report(state)
        message = _build_slack_message(report)
        header = message["blocks"][0]
        assert header["type"] == "header"
        assert "Test Suite" in header["text"]["text"]

    def test_includes_failure_details(self):
        state = _make_state_with_results()
        report = generate_report(state)
        message = _build_slack_message(report)
        # Find the block with "Failed Tests"
        text_blocks = [
            b for b in message["blocks"]
            if b.get("type") == "section" and "Failed Tests" in str(b)
        ]
        assert len(text_blocks) == 1


class TestSendSlackNotification:
    """Tests for send_slack_notification."""

    def test_skip_when_no_webhook(self):
        state = _make_state_with_results()
        report = generate_report(state)
        result = send_slack_notification(report, webhook_url="")
        assert result["sent"] is False
        assert "not set" in result["message"]

    def test_mock_post_success(self):
        def mock_post(url, payload):
            return {"status_code": 200, "body": "ok"}

        state = _make_state_with_results()
        report = generate_report(state)
        result = send_slack_notification(
            report,
            webhook_url="https://hooks.slack.com/test",
            post_fn=mock_post,
        )
        assert result["sent"] is True
        assert result["status_code"] == 200

    def test_mock_post_failure(self):
        def mock_post(url, payload):
            return {"status_code": 500, "body": "server error"}

        state = _make_state_with_results()
        report = generate_report(state)
        result = send_slack_notification(
            report,
            webhook_url="https://hooks.slack.com/test",
            post_fn=mock_post,
        )
        assert result["sent"] is False
        assert result["status_code"] == 500

    def test_mock_post_exception(self):
        def mock_post(url, payload):
            raise ConnectionError("network down")

        state = _make_state_with_results()
        report = generate_report(state)
        result = send_slack_notification(
            report,
            webhook_url="https://hooks.slack.com/test",
            post_fn=mock_post,
        )
        assert result["sent"] is False
        assert "network down" in result["message"]


class TestReportResults:
    """Tests for the report_results node function."""

    def test_populates_state_report(self):
        state = _make_state_with_results()
        state.config = {"report_dir": tempfile.mkdtemp()}
        result = report_results(state)
        assert result.report is not None
        assert result.report["suite_name"] == "Test Suite"
        assert result.completed_at != ""

    def test_slack_response_populated(self):
        state = _make_state_with_results()
        state.config = {
            "report_dir": tempfile.mkdtemp(),
            "slack_webhook_url": "",
        }
        result = report_results(state)
        assert result.slack_response is not None
        assert result.slack_response["sent"] is False

    def test_with_mock_slack(self):
        captured = {}

        def mock_post(url, payload):
            captured["url"] = url
            captured["payload"] = payload
            return {"status_code": 200, "body": "ok"}

        state = _make_state_with_results()
        state.config = {
            "report_dir": tempfile.mkdtemp(),
            "slack_webhook_url": "https://hooks.slack.com/test",
            "slack_post_fn": mock_post,
        }
        result = report_results(state)
        assert result.slack_response["sent"] is True
        assert captured["url"] == "https://hooks.slack.com/test"
        assert "blocks" in captured["payload"]
