# Author: Maharshi Soni | License: MIT
"""CLI entry point for the LangGraph QA Agent.

Usage examples::

    # Run all test templates against the default target
    python main.py

    # Specify a target URL and suite name
    python main.py --url https://myapp.example.com --suite "Regression Suite"

    # Run only specific templates
    python main.py --templates login_flow search_flow

    # Filter by tags
    python main.py --tags smoke critical

    # Send results to Slack
    python main.py --slack-webhook https://hooks.slack.com/services/T.../B.../xxx

    # Set a custom report output directory
    python main.py --report-dir ./my_reports

    # Enable verbose logging
    python main.py -v
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List, Optional

from core.bug_analyzer import analyze_bugs
from core.graph import GraphBuilder
from core.reporter import report_results
from core.self_healer import heal_and_retry
from core.state import AgentState, NodeName, TestStatus
from core.test_executor import execute_tests
from core.test_planner import get_available_templates, plan_tests


def _build_router(state: AgentState) -> NodeName:
    """Conditional router evaluated after test execution.

    Routing logic:
    - If there are failures -> BUG_ANALYZER
    - If all tests passed   -> REPORTER (skip analysis + healing)
    """
    has_failures = any(
        tc.status in (TestStatus.FAILED, TestStatus.ERROR)
        for tc in state.test_cases
    )
    if has_failures:
        return NodeName.BUG_ANALYZER
    return NodeName.REPORTER


def _heal_router(state: AgentState) -> NodeName:
    """Conditional router evaluated after bug analysis.

    Routing logic:
    - If healing is recommended -> SELF_HEALER
    - Otherwise                 -> REPORTER
    """
    if state.should_heal:
        return NodeName.SELF_HEALER
    return NodeName.REPORTER


def build_agent_graph() -> "CompiledGraph":  # noqa: F821
    """Construct and compile the full QA agent graph.

    Graph topology::

        TEST_PLANNER
              |
        TEST_EXECUTOR
            / \\
      (failures?)  (all pass?)
          |              |
    BUG_ANALYZER     REPORTER -> END
        / \\
  (healable?) (not healable?)
      |              |
  SELF_HEALER    REPORTER -> END
      |
    REPORTER -> END
    """
    builder = GraphBuilder()

    # Register nodes
    builder.add_node(NodeName.TEST_PLANNER, plan_tests)
    builder.add_node(NodeName.TEST_EXECUTOR, execute_tests)
    builder.add_node(NodeName.BUG_ANALYZER, analyze_bugs)
    builder.add_node(NodeName.SELF_HEALER, heal_and_retry)
    builder.add_node(NodeName.REPORTER, report_results)

    # Fixed edges
    builder.add_edge(NodeName.TEST_PLANNER, NodeName.TEST_EXECUTOR)
    builder.add_edge(NodeName.SELF_HEALER, NodeName.REPORTER)
    builder.add_edge(NodeName.REPORTER, NodeName.END)

    # Conditional edges
    builder.add_conditional_edge(
        NodeName.TEST_EXECUTOR,
        _build_router,
        {
            NodeName.BUG_ANALYZER: NodeName.BUG_ANALYZER,
            NodeName.REPORTER: NodeName.REPORTER,
        },
    )
    builder.add_conditional_edge(
        NodeName.BUG_ANALYZER,
        _heal_router,
        {
            NodeName.SELF_HEALER: NodeName.SELF_HEALER,
            NodeName.REPORTER: NodeName.REPORTER,
        },
    )

    builder.set_entry_point(NodeName.TEST_PLANNER)
    return builder.compile()


def _print_summary(state: AgentState) -> None:
    """Print a human-readable summary to stdout."""
    report = state.report
    if not report:
        print("\n[!] No report generated.")
        return

    summary = report["summary"]
    counts = summary["counts"]

    print("\n" + "=" * 60)
    print(f"  {report['suite_name']} - Test Report")
    print("=" * 60)
    print(f"  Run ID   : {report['run_id']}")
    print(f"  Target   : {report['target_url']}")
    print(f"  Started  : {report['started_at']}")
    print(f"  Completed: {report['completed_at']}")
    print("-" * 60)
    print(f"  Total    : {summary['total_tests']}")
    print(f"  Passed   : {counts['passed']}")
    print(f"  Failed   : {counts['failed']}")
    print(f"  Errors   : {counts['error']}")
    print(f"  Healed   : {counts['healed']}")
    print(f"  Skipped  : {counts['skipped']}")
    print(f"  Pass Rate: {summary['pass_rate']}%")
    print(f"  Duration : {summary['total_duration_ms']:.0f} ms")
    print("-" * 60)

    if summary["healed_locators"] > 0:
        print(f"  Self-Healed Locators: {summary['healed_locators']}")
        for hl in report.get("healed_locators", []):
            print(
                f"    {hl['test_id']} step {hl['step_index']}: "
                f"{hl['original']['value']} -> {hl['healed']['value']}"
            )
        print("-" * 60)

    # Per-test summary
    for tc in report.get("test_cases", []):
        status_marker = {
            "passed": "[PASS]",
            "failed": "[FAIL]",
            "error": "[ERR ]",
            "healed": "[HEAL]",
            "skipped": "[SKIP]",
        }.get(tc["status"], "[????]")
        line = f"  {status_marker} {tc['test_id']} {tc['name']}"
        if tc.get("error_summary"):
            line += f"\n           {tc['error_summary'][:80]}"
        if tc.get("bug_analysis"):
            ba = tc["bug_analysis"]
            line += (
                f"\n           Category: {ba['category']} | "
                f"Severity: {ba['severity']} | "
                f"Healable: {ba['healable']}"
            )
        print(line)

    print("=" * 60)

    # Slack status
    slack = state.slack_response
    if slack and slack.get("sent"):
        print("  Slack notification sent successfully.")
    elif slack:
        print(f"  Slack notification skipped: {slack.get('message', '')}")

    print()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="langgraph-qa-agent",
        description="Autonomous QA testing agent with self-healing locators.",
    )
    parser.add_argument(
        "--url",
        default="https://example.com",
        help="Target URL to test (default: https://example.com)",
    )
    parser.add_argument(
        "--suite",
        default="LangGraph QA Suite",
        help="Name for the test suite (default: LangGraph QA Suite)",
    )
    parser.add_argument(
        "--templates",
        nargs="*",
        default=None,
        help=(
            "Test templates to run (default: all). "
            f"Available: {', '.join(get_available_templates())}"
        ),
    )
    parser.add_argument(
        "--tags",
        nargs="*",
        default=None,
        help="Only run templates matching these tags.",
    )
    parser.add_argument(
        "--slack-webhook",
        default="",
        help="Slack incoming webhook URL for notifications.",
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory to save JSON reports (default: reports).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON report to stdout instead of a summary.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point. Returns 0 on all-pass, 1 if any test failed."""
    args = parse_args(argv)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build initial state
    config = {
        "report_dir": args.report_dir,
        "slack_webhook_url": args.slack_webhook,
    }
    if args.templates:
        config["templates"] = args.templates
    if args.tags:
        config["tags"] = args.tags

    state = AgentState(
        target_url=args.url,
        test_suite_name=args.suite,
        config=config,
    )

    # Build and run the graph
    graph = build_agent_graph()
    final_state = graph.run(state)

    # Output results
    if args.json:
        print(json.dumps(final_state.report, indent=2))
    else:
        _print_summary(final_state)

    # Exit code: 0 if all passed/healed, 1 otherwise
    has_real_failures = any(
        tc.status in (TestStatus.FAILED, TestStatus.ERROR)
        for tc in final_state.test_cases
    )
    return 1 if has_real_failures else 0


if __name__ == "__main__":
    sys.exit(main())
