# Author: Maharshi Soni | License: MIT
"""Self-healing locator node for the QA agent graph.

When the bug analyzer flags a failure as ``healable`` (i.e. the root cause is
a broken CSS or XPath selector), this node attempts to automatically find an
alternative locator that resolves in the current DOM.

Healing strategies:

1. **Alternative selector lookup** -- Checks a registry of known alternative
   selectors (simulating a historical locator database).
2. **Attribute relaxation** -- Strips specificity from CSS selectors (e.g.
   removes nth-child, loosens class chains) and retries.
3. **Strategy switch** -- Converts a CSS selector to an XPath equivalent or
   vice versa to see if a different strategy resolves.

After healing, the node replaces the broken locator on the test step and
marks the step for re-execution.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from core.state import AgentState, Locator, TestCase, TestStatus
from core.test_executor import ALTERNATIVE_SELECTORS, _KNOWN_SELECTORS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Healing strategies
# ---------------------------------------------------------------------------

def _try_alternative_lookup(locator: Locator) -> Optional[Locator]:
    """Check the alternative selector registry for a replacement."""
    alt = ALTERNATIVE_SELECTORS.get(locator.value)
    if alt:
        logger.debug("  Found alternative selector for '%s'", locator.value)
        return Locator(
            strategy=alt["strategy"],
            value=alt["value"],
            description=alt.get("description", locator.description),
            confidence=0.85,
        )
    return None


def _try_attribute_relaxation(locator: Locator) -> Optional[Locator]:
    """Relax a CSS selector by removing restrictive pseudo-classes or nesting."""
    if locator.strategy != "css":
        return None

    value = locator.value
    # Remove :nth-child(...), :first-child, :last-child
    relaxed = re.sub(r":(?:nth-child\([^)]*\)|first-child|last-child)", "", value)
    # Remove direct-child combinators (replace > with space)
    relaxed = relaxed.replace(" > ", " ")
    # Remove attribute substring selectors like [class*='...']
    relaxed = re.sub(r"\[class\*=['\"][^'\"]*['\"]\]", "", relaxed)

    relaxed = relaxed.strip()
    if relaxed and relaxed != value and relaxed in _KNOWN_SELECTORS:
        logger.debug("  Relaxed selector '%s' -> '%s'", value, relaxed)
        return Locator(
            strategy="css",
            value=relaxed,
            description=f"{locator.description} (relaxed)",
            confidence=0.70,
        )
    return None


def _try_strategy_switch(locator: Locator) -> Optional[Locator]:
    """Convert between CSS and XPath to try a different resolution path."""
    if locator.strategy == "css":
        # Simple CSS ID selector -> XPath
        id_match = re.match(r"^#([\w-]+)$", locator.value)
        if id_match:
            xpath_value = f"//*[@id='{id_match.group(1)}']"
            return Locator(
                strategy="xpath",
                value=xpath_value,
                description=f"{locator.description} (css->xpath)",
                confidence=0.65,
            )
        # Simple CSS class selector -> XPath
        class_match = re.match(r"^\.([\w-]+)$", locator.value)
        if class_match:
            xpath_value = f"//*[contains(@class, '{class_match.group(1)}')]"
            return Locator(
                strategy="xpath",
                value=xpath_value,
                description=f"{locator.description} (css->xpath)",
                confidence=0.60,
            )
    elif locator.strategy == "xpath":
        # Simple XPath class contains -> CSS
        class_match = re.search(
            r"contains\(@class,\s*'([\w-]+)'\)", locator.value
        )
        if class_match:
            css_value = f".{class_match.group(1)}"
            if css_value in _KNOWN_SELECTORS:
                return Locator(
                    strategy="css",
                    value=css_value,
                    description=f"{locator.description} (xpath->css)",
                    confidence=0.65,
                )
    return None


def heal_locator(locator: Locator) -> Optional[Locator]:
    """Attempt to heal a broken locator using all available strategies.

    Returns a replacement ``Locator`` on success, or ``None`` if healing fails.
    """
    strategies = [
        ("alternative_lookup", _try_alternative_lookup),
        ("attribute_relaxation", _try_attribute_relaxation),
        ("strategy_switch", _try_strategy_switch),
    ]

    for name, strategy_fn in strategies:
        result = strategy_fn(locator)
        if result is not None:
            logger.info(
                "  Healed '%s' via %s -> '%s' (confidence=%.2f)",
                locator.value,
                name,
                result.value,
                result.confidence,
            )
            return result

    logger.warning("  Could not heal locator '%s'", locator.value)
    return None


def heal_and_retry(state: AgentState) -> AgentState:
    """Self-healer node: attempts to fix broken locators and re-execute.

    For each failed step flagged as a locator issue:
    1. Attempt to find an alternative locator.
    2. If found, attach it to the step and re-run the test case.
    3. Record the healing event in ``state.healed_locators``.
    """
    if not state.should_heal:
        logger.info("No healing needed.")
        return state

    logger.info("Attempting to heal %d locator failure(s)...", len(state.failed_steps))

    # Index test cases by ID
    tc_index: Dict[str, TestCase] = {tc.test_id: tc for tc in state.test_cases}
    healed_locators: List[Dict[str, Any]] = []

    for failure in state.failed_steps:
        if not failure.get("is_locator_failure"):
            continue

        test_id = failure["test_id"]
        step_index = failure["step_index"]
        tc = tc_index.get(test_id)
        if tc is None:
            continue

        step = tc.steps[step_index]
        if step.locator is None:
            continue

        healed = heal_locator(step.locator)
        if healed is not None:
            step.healed_locator = healed
            healed_locators.append(
                {
                    "test_id": test_id,
                    "step_index": step_index,
                    "original": step.locator.to_dict(),
                    "healed": healed.to_dict(),
                }
            )

            # Re-execute just the failed test case
            _re_execute_healed_test(tc)

    state.healed_locators = healed_locators
    state.should_heal = False
    state.should_retry = False

    logger.info("Healing complete. %d locator(s) healed.", len(healed_locators))
    return state


def _re_execute_healed_test(tc: TestCase) -> None:
    """Re-run a test case after locator healing.

    Imports execute logic inline to avoid circular imports at module level.
    """
    from core.test_executor import _dispatch_action

    logger.info("Re-executing healed test: %s (%s)", tc.name, tc.test_id)
    tc.retry_count += 1
    total_duration = 0.0
    all_passed = True

    for idx, step in enumerate(tc.steps):
        # Reset previously skipped steps
        if step.status == TestStatus.SKIPPED:
            step.status = TestStatus.SKIPPED  # will be set by dispatch

        step = _dispatch_action(step)
        tc.steps[idx] = step
        total_duration += step.duration_ms

        if step.status in (TestStatus.FAILED, TestStatus.ERROR):
            all_passed = False
            for remaining in tc.steps[idx + 1 :]:
                remaining.status = TestStatus.SKIPPED
            break

    tc.duration_ms = round(total_duration, 2)

    if all_passed:
        tc.status = TestStatus.HEALED
        tc.error_summary = ""
        logger.info("  Test %s HEALED after retry.", tc.test_id)
    else:
        failed_step = next(
            (s for s in tc.steps if s.status in (TestStatus.FAILED, TestStatus.ERROR)),
            None,
        )
        tc.error_summary = failed_step.error_message if failed_step else "Unknown"
        logger.warning("  Test %s still failing after healing.", tc.test_id)
