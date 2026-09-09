# Author: Maharshi Soni | License: MIT
"""Test execution node with simulated Playwright-style actions.

This module simulates the execution of test steps against a web application.
In a real integration the ``_dispatch_action`` function would delegate to
Playwright's ``page.click()``, ``page.fill()``, ``page.goto()``, and
assertion helpers. Here, execution is simulated using a configurable
synthetic DOM snapshot so the full graph pipeline can run end-to-end
without a live browser.

The executor walks through every test case in ``state.test_cases``, runs
each step, records pass/fail/error status, and populates ``state.failed_steps``
for downstream nodes (bug analyzer, self-healer) to consume.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List, Optional, Set

from core.state import AgentState, Locator, TestCase, TestStep, TestStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synthetic DOM snapshot
# ---------------------------------------------------------------------------

# Simulates which CSS/XPath selectors "exist" in the target page.  A selector
# that appears in this set will resolve successfully; one that does not will
# trigger a "locator not found" failure, exercising the self-healing path.

_KNOWN_SELECTORS: Set[str] = {
    # Login page
    "#login-form",
    "input[name='username']",
    "input[name='password']",
    "button[type='submit']",
    # NOTE: ".welcome-message" intentionally MISSING to trigger healing
    # Search page
    "#search-input",
    ".search-btn",
    ".search-results",
    # Navigation
    "nav.main-nav",
    "a[href='/about']",
    "h1.page-title",
    # Contact form
    "button.submit-btn",
    ".error-message",
    "input[name='email']",
    ".email-error",
    # Responsive
    ".hero-section",
    "footer.site-footer",
    # NOTE: xpath "//div[contains(@class, 'sidebar')]" intentionally MISSING
    # Alternative selectors (exist in DOM under different names)
    ".user-greeting",
    "aside.sidebar-panel",
}

# Selectors that exist under alternative locators (for self-healing)
ALTERNATIVE_SELECTORS: Dict[str, Dict[str, str]] = {
    ".welcome-message": {
        "strategy": "css",
        "value": ".user-greeting",
        "description": "Welcome banner (healed)",
    },
    "//div[contains(@class, 'sidebar')]": {
        "strategy": "css",
        "value": "aside.sidebar-panel",
        "description": "Sidebar panel (healed from xpath)",
    },
}

# Text content returned by certain selectors
_ELEMENT_TEXT: Dict[str, str] = {
    ".user-greeting": "Welcome, Test User",
    "h1.page-title": "About Us",
    ".error-message": "Please fill in all required fields",
    ".email-error": "Please enter a valid email",
}


def _selector_exists(locator: Locator) -> bool:
    """Check whether a locator resolves in the synthetic DOM."""
    return locator.value in _KNOWN_SELECTORS


def _get_element_text(locator: Locator) -> Optional[str]:
    """Return the synthetic text content for a resolved locator."""
    return _ELEMENT_TEXT.get(locator.value)


def _dispatch_action(step: TestStep) -> TestStep:
    """Simulate executing a single test step.

    Updates the step's ``status``, ``error_message``, and ``duration_ms``.
    """
    start = time.perf_counter()

    # Use healed locator if one has been set
    active_locator = step.healed_locator or step.locator

    try:
        if step.action == "navigate":
            # Navigation always succeeds in the simulation
            step.status = TestStatus.PASSED
            logger.debug("  Navigated to %s", step.value)

        elif step.action in ("click", "type", "assert_visible"):
            if active_locator is None:
                step.status = TestStatus.ERROR
                step.error_message = "No locator provided for action."
            elif not _selector_exists(active_locator):
                step.status = TestStatus.FAILED
                step.error_message = (
                    f"Locator not found: "
                    f"{active_locator.strategy}={active_locator.value}"
                )
            else:
                step.status = TestStatus.PASSED

        elif step.action == "assert_text":
            if active_locator is None:
                step.status = TestStatus.ERROR
                step.error_message = "No locator provided for assert_text."
            elif not _selector_exists(active_locator):
                step.status = TestStatus.FAILED
                step.error_message = (
                    f"Locator not found: "
                    f"{active_locator.strategy}={active_locator.value}"
                )
            else:
                actual_text = _get_element_text(active_locator)
                if actual_text == step.value:
                    step.status = TestStatus.PASSED
                else:
                    step.status = TestStatus.FAILED
                    step.error_message = (
                        f"Text mismatch: expected '{step.value}', "
                        f"got '{actual_text}'"
                    )
        else:
            step.status = TestStatus.ERROR
            step.error_message = f"Unknown action: {step.action}"

    except Exception as exc:
        step.status = TestStatus.ERROR
        step.error_message = str(exc)

    # Simulate realistic timing (5-50 ms per step)
    elapsed = (time.perf_counter() - start) * 1000
    step.duration_ms = round(max(elapsed, random.uniform(5.0, 50.0)), 2)
    return step


def _execute_test_case(test_case: TestCase) -> TestCase:
    """Run all steps in a test case sequentially.

    If a step fails, subsequent steps are skipped (fail-fast within a case).
    """
    logger.info("Executing test: %s (%s)", test_case.name, test_case.test_id)
    total_duration = 0.0

    for idx, step in enumerate(test_case.steps):
        step = _dispatch_action(step)
        test_case.steps[idx] = step
        total_duration += step.duration_ms

        if step.status in (TestStatus.FAILED, TestStatus.ERROR):
            logger.warning(
                "  Step %d FAILED: %s — %s",
                idx + 1,
                step.description,
                step.error_message,
            )
            # Skip remaining steps
            for remaining in test_case.steps[idx + 1 :]:
                remaining.status = TestStatus.SKIPPED
            break
        else:
            logger.debug("  Step %d PASSED: %s", idx + 1, step.description)

    # Determine overall test case status
    statuses = [s.status for s in test_case.steps]
    if TestStatus.ERROR in statuses:
        test_case.status = TestStatus.ERROR
    elif TestStatus.FAILED in statuses:
        test_case.status = TestStatus.FAILED
    elif all(s == TestStatus.PASSED for s in statuses):
        test_case.status = TestStatus.PASSED
    else:
        test_case.status = TestStatus.SKIPPED

    test_case.duration_ms = round(total_duration, 2)

    if test_case.status == TestStatus.FAILED:
        failed_step = next(
            s for s in test_case.steps if s.status == TestStatus.FAILED
        )
        test_case.error_summary = failed_step.error_message

    logger.info(
        "Test %s result: %s (%.1f ms)",
        test_case.test_id,
        test_case.status.value,
        test_case.duration_ms,
    )
    return test_case


def execute_tests(state: AgentState) -> AgentState:
    """Test executor node: runs every test case and records failures.

    Populates ``state.failed_steps`` with metadata about each failure so
    the bug analyzer and self-healer can process them.
    """
    logger.info(
        "Executing %d test case(s) against %s",
        len(state.test_cases),
        state.target_url,
    )

    failed_steps: List[Dict[str, Any]] = []

    for idx, tc in enumerate(state.test_cases):
        tc = _execute_test_case(tc)
        state.test_cases[idx] = tc

        # Collect failed steps for downstream processing
        if tc.status in (TestStatus.FAILED, TestStatus.ERROR):
            for step_idx, step in enumerate(tc.steps):
                if step.status in (TestStatus.FAILED, TestStatus.ERROR):
                    failed_steps.append(
                        {
                            "test_id": tc.test_id,
                            "test_name": tc.name,
                            "step_index": step_idx,
                            "action": step.action,
                            "locator": step.locator.to_dict() if step.locator else None,
                            "error_message": step.error_message,
                            "is_locator_failure": "Locator not found" in step.error_message,
                        }
                    )

    state.failed_steps = failed_steps

    passed = sum(1 for tc in state.test_cases if tc.status == TestStatus.PASSED)
    failed = sum(1 for tc in state.test_cases if tc.status in (TestStatus.FAILED, TestStatus.ERROR))
    logger.info(
        "Execution complete: %d passed, %d failed out of %d total.",
        passed,
        failed,
        len(state.test_cases),
    )
    return state
