# Author: Maharshi Soni | License: MIT
"""Test planning node for the QA agent graph.

The test planner generates a structured test plan based on the target URL
and configuration. It produces a set of synthetic test cases that exercise
common web application flows: navigation, form submission, element visibility,
authentication, and content validation.

In a production system this node would use page crawling or an LLM to derive
test cases from the actual page structure; here it uses curated synthetic
templates that mirror realistic SDET workflows.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.state import AgentState, Locator, TestCase, TestStep, TestStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synthetic test templates
# ---------------------------------------------------------------------------

_LOGIN_STEPS = [
    TestStep(
        action="navigate",
        value="{base_url}/login",
        description="Navigate to the login page",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", "#login-form", "Login form container"),
        description="Verify login form is visible",
    ),
    TestStep(
        action="type",
        locator=Locator("css", "input[name='username']", "Username field"),
        value="testuser@example.com",
        description="Enter username",
    ),
    TestStep(
        action="type",
        locator=Locator("css", "input[name='password']", "Password field"),
        value="SecureP@ss123",
        description="Enter password",
    ),
    TestStep(
        action="click",
        locator=Locator("css", "button[type='submit']", "Submit button"),
        description="Click the login button",
    ),
    TestStep(
        action="assert_text",
        locator=Locator("css", ".welcome-message", "Welcome banner"),
        value="Welcome, Test User",
        description="Verify welcome message appears after login",
    ),
]

_SEARCH_STEPS = [
    TestStep(
        action="navigate",
        value="{base_url}/search",
        description="Navigate to the search page",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", "#search-input", "Search input box"),
        description="Verify search input is visible",
    ),
    TestStep(
        action="type",
        locator=Locator("css", "#search-input", "Search input box"),
        value="test automation",
        description="Type a search query",
    ),
    TestStep(
        action="click",
        locator=Locator("css", ".search-btn", "Search button"),
        description="Click search button",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", ".search-results", "Results container"),
        description="Verify search results are displayed",
    ),
]

_NAVIGATION_STEPS = [
    TestStep(
        action="navigate",
        value="{base_url}",
        description="Navigate to the home page",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", "nav.main-nav", "Main navigation bar"),
        description="Verify main navigation is visible",
    ),
    TestStep(
        action="click",
        locator=Locator("css", "a[href='/about']", "About link"),
        description="Click the About link",
    ),
    TestStep(
        action="assert_text",
        locator=Locator("css", "h1.page-title", "Page title heading"),
        value="About Us",
        description="Verify About page title",
    ),
]

_FORM_VALIDATION_STEPS = [
    TestStep(
        action="navigate",
        value="{base_url}/contact",
        description="Navigate to the contact form",
    ),
    TestStep(
        action="click",
        locator=Locator("css", "button.submit-btn", "Submit button"),
        description="Click submit without filling fields",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", ".error-message", "Validation error message"),
        description="Verify validation error is shown",
    ),
    TestStep(
        action="type",
        locator=Locator("css", "input[name='email']", "Email field"),
        value="invalid-email",
        description="Enter an invalid email address",
    ),
    TestStep(
        action="click",
        locator=Locator("css", "button.submit-btn", "Submit button"),
        description="Click submit with invalid email",
    ),
    TestStep(
        action="assert_text",
        locator=Locator("css", ".email-error", "Email error message"),
        value="Please enter a valid email",
        description="Verify email validation error text",
    ),
]

_RESPONSIVE_STEPS = [
    TestStep(
        action="navigate",
        value="{base_url}",
        description="Navigate to the home page",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", ".hero-section", "Hero section"),
        description="Verify hero section is visible on desktop",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator("css", "footer.site-footer", "Site footer"),
        description="Verify footer is visible",
    ),
    TestStep(
        action="assert_visible",
        locator=Locator(
            "xpath",
            "//div[contains(@class, 'sidebar')]",
            "Sidebar panel",
        ),
        description="Verify sidebar is present",
    ),
]

_TEMPLATE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "login_flow": {
        "name": "User Login Flow",
        "description": "Verify end-to-end login with valid credentials",
        "tags": ["smoke", "auth", "critical"],
        "steps": _LOGIN_STEPS,
    },
    "search_flow": {
        "name": "Search Functionality",
        "description": "Verify search input, submission, and results rendering",
        "tags": ["functional", "search"],
        "steps": _SEARCH_STEPS,
    },
    "navigation_flow": {
        "name": "Site Navigation",
        "description": "Verify main navigation links and page transitions",
        "tags": ["smoke", "navigation"],
        "steps": _NAVIGATION_STEPS,
    },
    "form_validation": {
        "name": "Contact Form Validation",
        "description": "Verify client-side form validation rules",
        "tags": ["functional", "forms", "validation"],
        "steps": _FORM_VALIDATION_STEPS,
    },
    "responsive_layout": {
        "name": "Responsive Layout Check",
        "description": "Verify key layout elements render on the page",
        "tags": ["visual", "responsive"],
        "steps": _RESPONSIVE_STEPS,
    },
}


def get_available_templates() -> List[str]:
    """Return the list of available test template names."""
    return list(_TEMPLATE_REGISTRY.keys())


def _build_test_case(
    template_key: str, base_url: str, template: Dict[str, Any]
) -> TestCase:
    """Instantiate a TestCase from a template, substituting the base URL."""
    steps: List[TestStep] = []
    for step in template["steps"]:
        new_step = TestStep(
            action=step.action,
            locator=step.locator,
            value=step.value.format(base_url=base_url) if step.value else step.value,
            description=step.description,
            status=TestStatus.SKIPPED,
        )
        steps.append(new_step)

    return TestCase(
        name=template["name"],
        description=template["description"],
        tags=list(template["tags"]),
        steps=steps,
    )


def plan_tests(state: AgentState) -> AgentState:
    """Test planner node: generates test cases from templates.

    Reads ``state.config`` for optional keys:

    - ``templates``: list of template keys to include (default: all).
    - ``tags``: only include templates whose tags overlap with this list.

    Populates ``state.test_cases`` and routes to the executor.
    """
    logger.info("Planning tests for target: %s", state.target_url)

    requested_templates = state.config.get("templates", None)
    requested_tags = set(state.config.get("tags", []))

    test_cases: List[TestCase] = []

    for key, template in _TEMPLATE_REGISTRY.items():
        # Filter by template name if specified
        if requested_templates and key not in requested_templates:
            continue
        # Filter by tags if specified
        if requested_tags and not requested_tags.intersection(template["tags"]):
            continue

        tc = _build_test_case(key, state.target_url, template)
        test_cases.append(tc)
        logger.info("  Planned: %s (%s)", tc.name, tc.test_id)

    state.test_cases = test_cases
    state.current_test_index = 0

    logger.info("Test plan complete: %d test case(s) generated.", len(test_cases))
    return state
