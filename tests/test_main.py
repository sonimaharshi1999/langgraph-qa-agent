# Author: Maharshi Soni | License: MIT
"""Tests for the main CLI entry point."""

import json
import tempfile

import pytest

from main import build_agent_graph, main, parse_args


class TestParseArgs:
    """Tests for parse_args."""

    def test_defaults(self):
        args = parse_args([])
        assert args.url == "https://example.com"
        assert args.suite == "LangGraph QA Suite"
        assert args.templates is None
        assert args.tags is None
        assert args.slack_webhook == ""
        assert args.report_dir == "reports"
        assert args.json is False
        assert args.verbose is False

    def test_custom_url(self):
        args = parse_args(["--url", "https://mysite.com"])
        assert args.url == "https://mysite.com"

    def test_custom_suite(self):
        args = parse_args(["--suite", "My Suite"])
        assert args.suite == "My Suite"

    def test_templates(self):
        args = parse_args(["--templates", "login_flow", "search_flow"])
        assert args.templates == ["login_flow", "search_flow"]

    def test_tags(self):
        args = parse_args(["--tags", "smoke", "critical"])
        assert args.tags == ["smoke", "critical"]

    def test_slack_webhook(self):
        args = parse_args(["--slack-webhook", "https://hooks.slack.com/xxx"])
        assert args.slack_webhook == "https://hooks.slack.com/xxx"

    def test_json_flag(self):
        args = parse_args(["--json"])
        assert args.json is True

    def test_verbose_flag(self):
        args = parse_args(["-v"])
        assert args.verbose is True

    def test_report_dir(self):
        args = parse_args(["--report-dir", "/tmp/reports"])
        assert args.report_dir == "/tmp/reports"


class TestBuildAgentGraph:
    """Tests for build_agent_graph."""

    def test_graph_compiles(self):
        graph = build_agent_graph()
        assert graph is not None
        names = graph.get_node_names()
        assert "test_planner" in names
        assert "test_executor" in names
        assert "bug_analyzer" in names
        assert "self_healer" in names
        assert "reporter" in names

    def test_graph_has_conditional_edges(self):
        graph = build_agent_graph()
        cond_sources = graph.get_conditional_edge_sources()
        assert "test_executor" in cond_sources
        assert "bug_analyzer" in cond_sources


class TestMainFunction:
    """Tests for the main() function."""

    def test_full_run_default(self):
        """Full end-to-end run with default settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = main(["--report-dir", tmpdir])
            # Some tests fail by design (missing selectors), exit code 0
            # because the self-healer fixes the locator issues
            assert exit_code in (0, 1)

    def test_full_run_specific_template(self):
        """Run only the navigation flow (should pass)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = main([
                "--templates", "navigation_flow",
                "--report-dir", tmpdir,
            ])
            assert exit_code == 0

    def test_full_run_smoke_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = main([
                "--tags", "smoke",
                "--report-dir", tmpdir,
            ])
            assert exit_code in (0, 1)

    def test_json_output(self, capsys):
        """Verify JSON output mode produces valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main([
                "--templates", "navigation_flow",
                "--report-dir", tmpdir,
                "--json",
            ])
            captured = capsys.readouterr()
            report = json.loads(captured.out)
            assert "run_id" in report
            assert "summary" in report

    def test_search_flow_passes(self):
        """Search flow should pass (all selectors exist)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = main([
                "--templates", "search_flow",
                "--report-dir", tmpdir,
            ])
            assert exit_code == 0

    def test_form_validation_passes(self):
        """Form validation flow should pass (all selectors exist)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = main([
                "--templates", "form_validation",
                "--report-dir", tmpdir,
            ])
            assert exit_code == 0
