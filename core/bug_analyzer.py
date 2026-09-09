# Author: Maharshi Soni | License: MIT
"""Bug analysis node for the QA agent graph.

When test execution produces failures, the bug analyzer examines each failed
step to determine:

- **Error category** (locator not found, text mismatch, timeout, etc.)
- **Root-cause hypothesis** based on keyword extraction and similarity to
  known bug patterns.
- **Severity** (critical / major / minor / cosmetic) using a rule-based scorer.
- **Whether self-healing might help** (only for locator-based failures).

The analysis results are attached to each ``TestCase.bug_analysis`` field and
the ``state.should_heal`` flag is set to route the graph toward the self-healer
when applicable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.nlp_engine import classify_error, extract_keywords, find_most_similar
from core.state import AgentState, TestStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known bug patterns (a small knowledge base for similarity matching)
# ---------------------------------------------------------------------------

_KNOWN_BUG_PATTERNS: List[str] = [
    "Element selector changed after a frontend deployment, causing locator not found errors.",
    "Text content was updated by the CMS but test assertions still expect the old copy.",
    "The page takes longer to render under load, causing timeout failures.",
    "A third-party script blocks the DOM, making elements invisible to the test runner.",
    "CSS class names were hashed differently after a build, breaking class-based selectors.",
    "An A/B test variant changed the page layout, moving elements outside the expected DOM path.",
    "A backend API returns an error, causing the frontend to display an error state instead of the expected UI.",
    "The element exists but is hidden behind a modal overlay.",
]

# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------

_SEVERITY_RULES: Dict[str, Dict[str, Any]] = {
    "locator_not_found": {
        "base_severity": "major",
        "critical_tags": ["critical", "smoke", "auth"],
    },
    "text_mismatch": {
        "base_severity": "minor",
        "critical_tags": ["critical"],
    },
    "timeout": {
        "base_severity": "major",
        "critical_tags": ["critical", "smoke"],
    },
    "network_error": {
        "base_severity": "critical",
        "critical_tags": [],
    },
    "unknown": {
        "base_severity": "minor",
        "critical_tags": ["critical"],
    },
}


def _compute_severity(category: str, tags: List[str]) -> str:
    """Determine severity from the error category and test-case tags."""
    rules = _SEVERITY_RULES.get(category, _SEVERITY_RULES["unknown"])
    base = rules["base_severity"]
    critical_tags = rules["critical_tags"]

    # Elevate severity if the test case carries a critical tag
    if any(t in critical_tags for t in tags):
        if base == "minor":
            return "major"
        if base == "major":
            return "critical"
    return base


def _build_analysis(
    error_message: str, tags: List[str]
) -> Dict[str, Any]:
    """Produce a structured bug analysis for a single error."""
    classification = classify_error(error_message)
    category: str = classification["category"]  # type: ignore[assignment]
    confidence: float = classification["confidence"]  # type: ignore[assignment]
    keywords = extract_keywords(error_message)

    # Find the most similar known bug pattern
    similar = find_most_similar(error_message, _KNOWN_BUG_PATTERNS, top_k=1)
    root_cause_hypothesis = similar[0][0] if similar else "No similar pattern found."
    pattern_similarity = similar[0][1] if similar else 0.0

    severity = _compute_severity(category, tags)

    return {
        "category": category,
        "classification_confidence": confidence,
        "severity": severity,
        "keywords": keywords,
        "root_cause_hypothesis": root_cause_hypothesis,
        "pattern_similarity": round(pattern_similarity, 4),
        "healable": category == "locator_not_found",
    }


def analyze_bugs(state: AgentState) -> AgentState:
    """Bug analyzer node: examines each failed test case and attaches analysis.

    Sets ``state.should_heal = True`` if any failure is a locator issue that
    the self-healer could potentially fix.
    """
    if not state.failed_steps:
        logger.info("No failures to analyze.")
        state.should_heal = False
        return state

    logger.info("Analyzing %d failure(s)...", len(state.failed_steps))

    healable_count = 0

    # Index test cases by ID for quick lookup
    tc_index = {tc.test_id: tc for tc in state.test_cases}

    for failure in state.failed_steps:
        test_id = failure["test_id"]
        tc = tc_index.get(test_id)
        if tc is None:
            continue

        analysis = _build_analysis(failure["error_message"], tc.tags)
        tc.bug_analysis = analysis

        if analysis["healable"]:
            healable_count += 1

        logger.info(
            "  %s [%s] severity=%s healable=%s hypothesis='%s'",
            tc.test_id,
            analysis["category"],
            analysis["severity"],
            analysis["healable"],
            analysis["root_cause_hypothesis"][:60] + "...",
        )

    state.should_heal = healable_count > 0
    logger.info(
        "Analysis complete. %d healable failure(s) detected.", healable_count
    )
    return state
