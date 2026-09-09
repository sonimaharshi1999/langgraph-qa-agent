# Author: Maharshi Soni | License: MIT
"""Result reporting and Slack webhook node for the QA agent graph.

This module generates a structured JSON test report and optionally sends a
summary to a Slack channel via an incoming webhook URL. The Slack integration
is designed to be fully mockable for testing -- supply a custom ``post_fn``
or set the webhook URL to an empty string to skip delivery.

The reporter also writes the full JSON report to disk under the ``reports/``
directory, named by run ID and timestamp.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.state import AgentState, TestStatus

logger = logging.getLogger(__name__)

# Type alias for the HTTP post function (mockable)
PostFunction = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def _default_post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Default HTTP POST implementation using urllib (no requests dependency).

    Returns a dict with ``status_code`` and ``body``.
    """
    import urllib.request
    import urllib.error

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"status_code": resp.status, "body": body}
    except urllib.error.HTTPError as exc:
        return {"status_code": exc.code, "body": str(exc.reason)}
    except urllib.error.URLError as exc:
        return {"status_code": 0, "body": str(exc.reason)}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _summarize_results(state: AgentState) -> Dict[str, Any]:
    """Compute aggregate test result metrics."""
    total = len(state.test_cases)
    counts = {
        "passed": 0,
        "failed": 0,
        "error": 0,
        "skipped": 0,
        "healed": 0,
    }
    for tc in state.test_cases:
        counts[tc.status.value] = counts.get(tc.status.value, 0) + 1

    total_duration = sum(tc.duration_ms for tc in state.test_cases)
    pass_rate = (counts["passed"] + counts["healed"]) / total * 100 if total else 0.0

    return {
        "total_tests": total,
        "counts": counts,
        "pass_rate": round(pass_rate, 1),
        "total_duration_ms": round(total_duration, 2),
        "healed_locators": len(state.healed_locators),
    }


def generate_report(state: AgentState) -> Dict[str, Any]:
    """Build the full JSON test report from the agent state."""
    summary = _summarize_results(state)

    report: Dict[str, Any] = {
        "run_id": state.run_id,
        "suite_name": state.test_suite_name,
        "target_url": state.target_url,
        "started_at": state.started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "test_cases": [tc.to_dict() for tc in state.test_cases],
        "healed_locators": state.healed_locators,
        "errors": state.errors,
    }
    return report


def save_report(report: Dict[str, Any], output_dir: str = "reports") -> str:
    """Write the report to a JSON file and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = report.get("run_id", "unknown")
    filename = f"report_{run_id}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    logger.info("Report saved to %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# Slack integration
# ---------------------------------------------------------------------------

def _build_slack_message(report: Dict[str, Any]) -> Dict[str, Any]:
    """Format a Slack-compatible message payload from the report."""
    summary = report["summary"]
    counts = summary["counts"]

    status_emoji = ":white_check_mark:" if counts["failed"] == 0 and counts["error"] == 0 else ":x:"

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{report['suite_name']} - Test Results",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status:* {status_emoji}"},
                {"type": "mrkdwn", "text": f"*Run ID:* `{report['run_id']}`"},
                {"type": "mrkdwn", "text": f"*Target:* {report['target_url']}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Pass Rate:* {summary['pass_rate']}%",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":test_tube: *Total:* {summary['total_tests']} | "
                    f":white_check_mark: *Passed:* {counts['passed']} | "
                    f":x: *Failed:* {counts['failed']} | "
                    f":warning: *Errors:* {counts['error']} | "
                    f":wrench: *Healed:* {counts['healed']} | "
                    f":fast_forward: *Skipped:* {counts['skipped']}"
                ),
            },
        },
    ]

    # Add failed test details
    failed_cases = [
        tc for tc in report.get("test_cases", [])
        if tc["status"] in ("failed", "error")
    ]
    if failed_cases:
        failure_lines = []
        for tc in failed_cases[:5]:  # Limit to 5 in Slack
            analysis = tc.get("bug_analysis", {})
            severity = analysis.get("severity", "unknown")
            failure_lines.append(
                f"- `{tc['test_id']}` {tc['name']} [{severity}]: {tc['error_summary'][:80]}"
            )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Failed Tests:*\n" + "\n".join(failure_lines),
                },
            }
        )

    # Healing summary
    if summary["healed_locators"] > 0:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":sparkles: *Self-Healing:* {summary['healed_locators']} "
                        f"locator(s) automatically repaired."
                    ),
                },
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Duration: {summary['total_duration_ms']:.0f} ms | "
                        f"Completed: {report['completed_at']}"
                    ),
                }
            ],
        }
    )

    return {"blocks": blocks}


def send_slack_notification(
    report: Dict[str, Any],
    webhook_url: str,
    post_fn: Optional[PostFunction] = None,
) -> Dict[str, Any]:
    """Send the test report summary to Slack.

    Args:
        report: The full test report dict.
        webhook_url: Slack incoming webhook URL. Empty string skips delivery.
        post_fn: Optional override for the HTTP POST function (for testing).

    Returns:
        A dict with ``sent`` (bool), ``status_code``, and ``message``.
    """
    if not webhook_url:
        logger.info("Slack webhook URL not configured; skipping notification.")
        return {"sent": False, "status_code": 0, "message": "Webhook URL not set."}

    payload = _build_slack_message(report)
    poster = post_fn or _default_post

    try:
        response = poster(webhook_url, payload)
        sent = response.get("status_code", 0) == 200
        logger.info(
            "Slack notification %s (status=%s).",
            "sent" if sent else "failed",
            response.get("status_code"),
        )
        return {
            "sent": sent,
            "status_code": response.get("status_code", 0),
            "message": response.get("body", ""),
        }
    except Exception as exc:
        logger.exception("Failed to send Slack notification.")
        return {"sent": False, "status_code": 0, "message": str(exc)}


# ---------------------------------------------------------------------------
# Graph node entry point
# ---------------------------------------------------------------------------

def report_results(state: AgentState) -> AgentState:
    """Reporter node: generates the report, saves it, and sends Slack notification.

    Reads ``state.config`` for:
    - ``slack_webhook_url``: URL for the Slack incoming webhook.
    - ``report_dir``: Directory to save JSON reports (default: ``reports``).
    - ``slack_post_fn``: Optional override POST function (for testing).
    """
    logger.info("Generating test report...")

    report = generate_report(state)
    state.report = report
    state.completed_at = report["completed_at"]

    # Save to disk
    report_dir = state.config.get("report_dir", "reports")
    save_report(report, output_dir=report_dir)

    # Slack notification
    webhook_url = state.config.get("slack_webhook_url", "")
    post_fn = state.config.get("slack_post_fn")
    slack_response = send_slack_notification(report, webhook_url, post_fn=post_fn)
    state.slack_response = slack_response

    logger.info("Reporting complete.")
    return state
