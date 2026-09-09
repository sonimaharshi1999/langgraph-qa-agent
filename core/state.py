# Author: Maharshi Soni | License: MIT
"""Shared state definitions for the QA agent graph.

The AgentState is a typed dictionary that flows through every node in the graph.
Each node reads from and writes to this shared state, enabling seamless data
passing between test planning, execution, analysis, healing, and reporting phases.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class TestStatus(Enum):
    """Possible outcomes for a single test case."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    HEALED = "healed"


class NodeName(Enum):
    """Identifiers for every node in the agent graph."""

    TEST_PLANNER = "test_planner"
    TEST_EXECUTOR = "test_executor"
    BUG_ANALYZER = "bug_analyzer"
    SELF_HEALER = "self_healer"
    REPORTER = "reporter"
    END = "__end__"


@dataclass
class Locator:
    """Represents a UI element locator used in test steps."""

    strategy: str  # css, xpath, id, name, text
    value: str
    description: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "value": self.value,
            "description": self.description,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Locator":
        return cls(
            strategy=data["strategy"],
            value=data["value"],
            description=data.get("description", ""),
            confidence=data.get("confidence", 1.0),
        )


@dataclass
class TestStep:
    """A single action within a test case."""

    action: str  # click, type, navigate, assert_visible, assert_text
    locator: Optional[Locator] = None
    value: Optional[str] = None
    description: str = ""
    status: TestStatus = TestStatus.SKIPPED
    error_message: str = ""
    healed_locator: Optional[Locator] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "action": self.action,
            "description": self.description,
            "status": self.status.value,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }
        if self.locator:
            result["locator"] = self.locator.to_dict()
        if self.value is not None:
            result["value"] = self.value
        if self.healed_locator:
            result["healed_locator"] = self.healed_locator.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestStep":
        locator = Locator.from_dict(data["locator"]) if "locator" in data else None
        healed = (
            Locator.from_dict(data["healed_locator"])
            if "healed_locator" in data
            else None
        )
        return cls(
            action=data["action"],
            locator=locator,
            value=data.get("value"),
            description=data.get("description", ""),
            status=TestStatus(data.get("status", "skipped")),
            error_message=data.get("error_message", ""),
            healed_locator=healed,
            duration_ms=data.get("duration_ms", 0.0),
        )


@dataclass
class TestCase:
    """A complete test case with multiple steps."""

    test_id: str = ""
    name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)
    status: TestStatus = TestStatus.SKIPPED
    retry_count: int = 0
    max_retries: int = 2
    error_summary: str = ""
    bug_analysis: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0

    def __post_init__(self) -> None:
        if not self.test_id:
            self.test_id = f"TC-{uuid.uuid4().hex[:8].upper()}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_summary": self.error_summary,
            "bug_analysis": self.bug_analysis,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        tc = cls(
            test_id=data.get("test_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            status=TestStatus(data.get("status", "skipped")),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 2),
            error_summary=data.get("error_summary", ""),
            bug_analysis=data.get("bug_analysis"),
            duration_ms=data.get("duration_ms", 0.0),
        )
        tc.steps = [TestStep.from_dict(s) for s in data.get("steps", [])]
        return tc


@dataclass
class AgentState:
    """The shared state that flows through every node in the graph.

    Each node reads the fields it needs, performs its work, and writes results
    back into the state before passing it to the next node.
    """

    # --- Input configuration ---
    target_url: str = "https://example.com"
    test_suite_name: str = "Default Suite"
    config: Dict[str, Any] = field(default_factory=dict)

    # --- Test plan and cases ---
    test_cases: List[TestCase] = field(default_factory=list)
    current_test_index: int = 0

    # --- Execution tracking ---
    failed_steps: List[Dict[str, Any]] = field(default_factory=list)
    healed_locators: List[Dict[str, Any]] = field(default_factory=list)

    # --- Routing control ---
    current_node: NodeName = NodeName.TEST_PLANNER
    next_node: Optional[NodeName] = None
    should_retry: bool = False
    should_heal: bool = False

    # --- Report data ---
    report: Optional[Dict[str, Any]] = None
    slack_response: Optional[Dict[str, Any]] = None

    # --- Metadata ---
    run_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    errors: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_url": self.target_url,
            "test_suite_name": self.test_suite_name,
            "config": self.config,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "current_test_index": self.current_test_index,
            "failed_steps": self.failed_steps,
            "healed_locators": self.healed_locators,
            "current_node": self.current_node.value,
            "next_node": self.next_node.value if self.next_node else None,
            "should_retry": self.should_retry,
            "should_heal": self.should_heal,
            "report": self.report,
            "slack_response": self.slack_response,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "errors": self.errors,
        }
