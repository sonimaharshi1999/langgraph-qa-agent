# LangGraph QA Agent

An autonomous, SDET-focused testing agent built with a LangGraph-style graph execution engine. It plans tests, executes them against a simulated DOM, analyzes failures with NLP, automatically heals broken CSS/XPath selectors, and generates structured JSON reports with optional Slack notifications -- all without paid APIs.

## Overview

Modern web applications change rapidly. Frontend deployments rename CSS classes, restructure DOM hierarchies, and update copy -- and every one of those changes can break end-to-end test suites overnight. SDETs spend a disproportionate amount of time triaging these "false" failures: figuring out whether the app is actually broken or whether the test's locator just drifted. **LangGraph QA Agent** automates that triage-and-repair cycle.

The agent is built around a **multi-node directed graph** that mirrors the LangGraph architecture: named processing nodes connected by fixed and conditional edges, with a shared state object flowing through the entire pipeline. Each node performs a distinct phase of the testing lifecycle -- planning, execution, bug analysis, self-healing, and reporting -- and conditional routing logic decides at runtime whether to retry a failed test, attempt locator healing, or proceed directly to reporting.

Unlike traditional test frameworks that simply mark a test as failed and move on, this agent **actively diagnoses failures** using a local NLP engine (sentence-transformers with a TF-IDF fallback) to classify error types, match them against known bug patterns, and determine whether the failure is a genuine application defect or a stale selector that can be automatically repaired. When a broken locator is detected, the self-healing node tries multiple repair strategies -- alternative selector lookup, attribute relaxation, and CSS/XPath strategy switching -- before re-executing the test.

Real-world use cases include nightly regression suites where locator drift is common, CI/CD pipelines that need intelligent failure triage before alerting the team, and QA platforms that want to reduce manual maintenance of element selectors. The agent produces detailed JSON reports suitable for dashboards and integrates with Slack via incoming webhooks so teams are notified immediately when tests complete.

The entire system runs locally with zero paid API dependencies. The NLP engine uses the open-source `all-MiniLM-L6-v2` sentence-transformers model for high-quality semantic analysis, and falls back gracefully to a built-in TF-IDF implementation when the model is not installed. Test execution uses a synthetic DOM simulation, so no live browser or Playwright installation is required to demonstrate the full pipeline.

## Features

- **Graph-based execution engine** -- Nodes, directed edges, and conditional routing implemented from scratch, mirroring the LangGraph architecture without requiring the `langgraph` package.
- **Test planning with templates** -- Generates structured test cases from curated templates covering login flows, search functionality, navigation, form validation, and responsive layout checks.
- **Simulated Playwright-style execution** -- Dispatches `click`, `type`, `navigate`, `assert_visible`, and `assert_text` actions against a synthetic DOM snapshot with realistic timing.
- **NLP-powered bug analysis** -- Classifies errors (locator not found, text mismatch, timeout, network error) using keyword matching and semantic similarity against a knowledge base of known bug patterns.
- **Self-healing locators** -- Automatically repairs broken CSS/XPath selectors using three strategies: alternative selector lookup, attribute relaxation, and strategy switching (CSS-to-XPath and vice versa).
- **Conditional routing** -- The graph dynamically routes through bug analysis and self-healing only when failures are detected, skipping unnecessary nodes when all tests pass.
- **Structured JSON reports** -- Every run produces a detailed JSON report with per-test results, bug analyses, healed locators, and aggregate metrics.
- **Slack webhook integration** -- Sends rich Block Kit messages to Slack channels with pass/fail summaries, failure details, and healing statistics. Fully mockable for testing.
- **No paid APIs** -- Uses `sentence-transformers` (open-source) for NLP, with a built-in TF-IDF fallback that requires no model download at all.
- **Comprehensive test suite** -- 70+ pytest tests covering every public function across all modules.

## Architecture / How It Works

The agent executes as a directed graph with five processing nodes and two conditional routing points:

```
                    +----------------+
                    | TEST_PLANNER   |  Generates test cases from templates
                    +-------+--------+
                            |
                    +-------v--------+
                    | TEST_EXECUTOR  |  Runs each test step against synthetic DOM
                    +-------+--------+
                            |
                     (has failures?)
                      /            \
                   YES              NO
                    |                |
            +-------v--------+      |
            | BUG_ANALYZER   |      |
            +-------+--------+      |
                    |               |
             (is healable?)         |
              /          \          |
           YES            NO        |
            |              |        |
    +-------v--------+    |        |
    | SELF_HEALER    |    |        |
    +-------+--------+    |        |
            |              |        |
            +---------+----+--------+
                      |
              +-------v--------+
              |   REPORTER     |  Generates JSON report + Slack notification
              +-------+--------+
                      |
                    [END]
```

**Shared State:** An `AgentState` dataclass flows through every node. Each node reads the fields it needs, performs its work, and writes results back. This eliminates inter-node coupling and makes the pipeline easy to extend.

**Conditional Routing:** After the executor, a router function inspects the state to decide whether to analyze failures or skip directly to reporting. After the bug analyzer, a second router checks whether any failures are "healable" (broken locators) and routes to the self-healer or the reporter accordingly.

**Self-Healing Pipeline:**
1. The executor detects that a CSS selector does not resolve in the DOM.
2. The bug analyzer classifies the error as `locator_not_found` with high confidence.
3. The self-healer tries three repair strategies in order:
   - **Alternative lookup:** checks a registry of known selector alternatives.
   - **Attribute relaxation:** strips restrictive pseudo-classes and combinators.
   - **Strategy switch:** converts CSS to XPath or vice versa.
4. If a working replacement is found, the healed locator is attached to the step and the test is re-executed.
5. A successfully healed test is marked `HEALED` instead of `FAILED`.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.9+ |
| Graph Engine | Custom implementation (LangGraph pattern) |
| NLP / Similarity | sentence-transformers (all-MiniLM-L6-v2) + built-in TF-IDF fallback |
| Test Execution | Simulated Playwright-style action dispatcher |
| Reporting | JSON + Slack Block Kit via incoming webhooks |
| Testing | pytest + pytest-cov |
| HTTP | urllib (stdlib, no `requests` dependency) |

## Getting Started

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- (Optional) A Slack incoming webhook URL for notifications

### Installation

```bash
# Clone the repository
git clone https://github.com/sonimaharshi1999/langgraph-qa-agent.git
cd langgraph-qa-agent

# Create and activate a virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Lightweight install (no model download):**

If you want to skip the sentence-transformers model download (~90 MB), the agent will automatically use the built-in TF-IDF fallback:

```bash
pip install pytest pytest-cov
```

### Configuration

The agent is configured entirely through CLI flags -- no config files or environment variables are required. Key options:

| Flag | Default | Description |
|---|---|---|
| `--url` | `https://example.com` | Target URL for test planning |
| `--suite` | `LangGraph QA Suite` | Name for the test suite |
| `--templates` | all | Space-separated list of template names |
| `--tags` | all | Filter templates by tag |
| `--slack-webhook` | (empty) | Slack incoming webhook URL |
| `--report-dir` | `reports` | Directory for JSON report output |
| `--json` | off | Print full JSON report to stdout |
| `-v` | off | Enable verbose (DEBUG) logging |

## Usage

### Run all tests with defaults

```bash
python main.py
```

### Target a specific URL with a custom suite name

```bash
python main.py --url https://staging.myapp.com --suite "Staging Regression"
```

### Run only specific test templates

```bash
python main.py --templates login_flow search_flow
```

Available templates: `login_flow`, `search_flow`, `navigation_flow`, `form_validation`, `responsive_layout`

### Filter by tags

```bash
python main.py --tags smoke critical
```

### Send results to Slack

```bash
python main.py --slack-webhook https://hooks.slack.com/services/T.../B.../xxxxx
```

### Get JSON output for CI/CD pipelines

```bash
python main.py --json > results.json
```

### Verbose mode for debugging

```bash
python main.py -v --templates login_flow
```

### Combine multiple options

```bash
python main.py \
  --url https://staging.myapp.com \
  --suite "Nightly Regression" \
  --tags smoke \
  --slack-webhook https://hooks.slack.com/services/T.../B.../xxxxx \
  --report-dir ./ci_reports \
  -v
```

## Sample Input / Output

### Scenario 1: All tests pass (navigation flow only)

```
$ python main.py --templates navigation_flow

============================================================
  LangGraph QA Suite - Test Report
============================================================
  Run ID   : RUN-A1B2C3D4E5F6
  Target   : https://example.com
  Started  : 2024-12-15T10:30:00.000000+00:00
  Completed: 2024-12-15T10:30:00.150000+00:00
------------------------------------------------------------
  Total    : 1
  Passed   : 1
  Failed   : 0
  Errors   : 0
  Healed   : 0
  Skipped  : 0
  Pass Rate: 100.0%
  Duration : 85 ms
------------------------------------------------------------
  [PASS] TC-8FA3B1C2 Site Navigation
============================================================
```

### Scenario 2: Full suite with self-healing

```
$ python main.py

============================================================
  LangGraph QA Suite - Test Report
============================================================
  Run ID   : RUN-D4E5F6A7B8C9
  Target   : https://example.com
  Started  : 2024-12-15T10:31:00.000000+00:00
  Completed: 2024-12-15T10:31:00.450000+00:00
------------------------------------------------------------
  Total    : 5
  Passed   : 3
  Failed   : 0
  Errors   : 0
  Healed   : 2
  Skipped  : 0
  Pass Rate: 100.0%
  Duration : 312 ms
------------------------------------------------------------
  Self-Healed Locators: 2
    TC-1A2B3C4D step 5: .welcome-message -> .user-greeting
    TC-9E8F7A6B step 3: //div[contains(@class, 'sidebar')] -> aside.sidebar-panel
------------------------------------------------------------
  [PASS] TC-1A2B3C4D User Login Flow
  [PASS] TC-5C6D7E8F Search Functionality
  [PASS] TC-8FA3B1C2 Site Navigation
  [PASS] TC-2B3C4D5E Contact Form Validation
  [HEAL] TC-9E8F7A6B Responsive Layout Check
============================================================
  Slack notification skipped: Webhook URL not set.
```

### Scenario 3: JSON output for CI integration

```
$ python main.py --templates search_flow --json
{
  "run_id": "RUN-F1E2D3C4B5A6",
  "suite_name": "LangGraph QA Suite",
  "target_url": "https://example.com",
  "started_at": "2024-12-15T10:32:00.000000+00:00",
  "completed_at": "2024-12-15T10:32:00.090000+00:00",
  "summary": {
    "total_tests": 1,
    "counts": {
      "passed": 1,
      "failed": 0,
      "error": 0,
      "skipped": 0,
      "healed": 0
    },
    "pass_rate": 100.0,
    "total_duration_ms": 62.35,
    "healed_locators": 0
  },
  "test_cases": [ ... ],
  "healed_locators": [],
  "errors": []
}
```

### Scenario 4: Verbose output showing graph traversal

```
$ python main.py --templates login_flow -v
10:33:00 [INFO] core.graph: === Graph execution started (run_id=RUN-A1B2C3D4E5F6) ===
10:33:00 [INFO] core.graph: Executing node: test_planner
10:33:00 [INFO] core.test_planner: Planning tests for target: https://example.com
10:33:00 [INFO] core.test_planner:   Planned: User Login Flow (TC-3F4A5B6C)
10:33:00 [INFO] core.test_planner: Test plan complete: 1 test case(s) generated.
10:33:00 [INFO] core.graph: Transition: test_planner -> test_executor
10:33:00 [INFO] core.graph: Executing node: test_executor
10:33:00 [INFO] core.test_executor: Executing 1 test case(s) against https://example.com
10:33:00 [INFO] core.test_executor: Executing test: User Login Flow (TC-3F4A5B6C)
10:33:00 [WARNING] core.test_executor:   Step 6 FAILED: Verify welcome message — Locator not found: css=.welcome-message
10:33:00 [INFO] core.graph: Conditional edge from test_executor resolved to bug_analyzer
10:33:00 [INFO] core.graph: Executing node: bug_analyzer
10:33:00 [INFO] core.bug_analyzer: Analyzing 1 failure(s)...
10:33:00 [INFO] core.bug_analyzer:   TC-3F4A5B6C [locator_not_found] severity=critical healable=True
10:33:00 [INFO] core.graph: Conditional edge from bug_analyzer resolved to self_healer
10:33:00 [INFO] core.graph: Executing node: self_healer
10:33:00 [INFO] core.self_healer:   Healed '.welcome-message' via alternative_lookup -> '.user-greeting'
10:33:00 [INFO] core.self_healer: Re-executing healed test: User Login Flow (TC-3F4A5B6C)
10:33:00 [INFO] core.self_healer:   Test TC-3F4A5B6C HEALED after retry.
10:33:00 [INFO] core.graph: Transition: self_healer -> reporter
10:33:00 [INFO] core.graph: Executing node: reporter
10:33:00 [INFO] core.reporter: Report saved to reports/report_RUN-A1B2C3D4E5F6_20241215_103300.json
10:33:00 [INFO] core.graph: === Graph execution completed ===
```

## Project Structure

```
langgraph-qa-agent/
├── main.py                  # CLI entry point
├── requirements.txt         # Pinned dependencies
├── .gitignore               # Git ignore rules
├── LICENSE                  # MIT License
├── README.md                # This file
├── core/
│   ├── __init__.py          # Package marker
│   ├── state.py             # AgentState, TestCase, TestStep, Locator, enums
│   ├── graph.py             # GraphBuilder, CompiledGraph, nodes, edges, routing
│   ├── test_planner.py      # Test planning node with template registry
│   ├── test_executor.py     # Simulated Playwright-style test execution
│   ├── bug_analyzer.py      # NLP-powered failure analysis and severity scoring
│   ├── self_healer.py       # Self-healing locator repair strategies
│   ├── nlp_engine.py        # Sentence-transformers + TF-IDF fallback NLP engine
│   └── reporter.py          # JSON report generation + Slack webhook integration
├── tests/
│   ├── __init__.py          # Package marker
│   ├── test_state.py        # Tests for state module
│   ├── test_graph.py        # Tests for graph engine
│   ├── test_planner.py      # Tests for test planner
│   ├── test_executor.py     # Tests for test executor
│   ├── test_nlp_engine.py   # Tests for NLP engine
│   ├── test_bug_analyzer.py # Tests for bug analyzer
│   ├── test_self_healer.py  # Tests for self-healer
│   ├── test_reporter.py     # Tests for reporter and Slack integration
│   └── test_main.py         # Tests for CLI and end-to-end pipeline
└── reports/
    └── .gitkeep             # Keeps the directory in version control
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=core --cov=main --cov-report=term-missing

# Run a specific test file
pytest tests/test_self_healer.py -v

# Run tests matching a keyword
pytest -k "heal" -v
```

Expected output:

```
$ pytest -v
========================= test session starts ==========================
tests/test_state.py::TestLocator::test_create_locator PASSED
tests/test_state.py::TestLocator::test_to_dict PASSED
tests/test_state.py::TestLocator::test_from_dict PASSED
...
tests/test_graph.py::TestCompiledGraph::test_linear_execution PASSED
tests/test_graph.py::TestCompiledGraph::test_conditional_routing PASSED
...
tests/test_self_healer.py::TestHealAndRetry::test_heal_updates_test_status PASSED
...
tests/test_main.py::TestMainFunction::test_full_run_default PASSED
tests/test_main.py::TestMainFunction::test_json_output PASSED
========================= 70+ passed in 2.5s ==========================
```

## Contributing

Contributions are welcome! To get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest -v`)
5. Commit with a clear message (`git commit -m "Add: my feature description"`)
6. Push to your branch (`git push origin feature/my-feature`)
7. Open a Pull Request

Please follow these conventions:
- Every Python file starts with `# Author: Maharshi Soni | License: MIT`
- All public functions must have docstrings
- New features must include pytest tests
- Keep the TF-IDF fallback working (do not make sentence-transformers mandatory)

## Roadmap

- [ ] **Live browser integration** -- Connect to real Playwright sessions for actual DOM interaction
- [ ] **LLM-powered test generation** -- Use local LLMs (Ollama, llama.cpp) to generate test cases from page screenshots
- [ ] **Historical locator database** -- Persist healed locators across runs so repairs are instant on re-occurrence
- [ ] **Visual regression testing** -- Screenshot comparison node using perceptual hashing
- [ ] **Parallel test execution** -- Run independent test cases concurrently with asyncio
- [ ] **GitHub Actions integration** -- Publish reports as PR comments and check annotations
- [ ] **Dashboard UI** -- Lightweight Flask/FastAPI dashboard for browsing test run history
- [ ] **Custom template authoring** -- YAML-based test template format for user-defined flows
- [ ] **Flaky test detection** -- Statistical analysis of test results across multiple runs
- [ ] **JIRA/Linear integration** -- Automatically create bug tickets for persistent failures

## Author

**Maharshi Soni**

- GitHub: [github.com/sonimaharshi1999](https://github.com/sonimaharshi1999)
- LinkedIn: [linkedin.com/in/maharshi-soni-b56736170](https://linkedin.com/in/maharshi-soni-b56736170)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [LangGraph](https://github.com/langchain-ai/langgraph) for the graph-based agent architecture pattern
- [sentence-transformers](https://www.sbert.net/) for the all-MiniLM-L6-v2 model used in semantic similarity
- [Playwright](https://playwright.dev/) for inspiring the test action dispatch model
- [Slack Block Kit](https://api.slack.com/block-kit) for the rich notification message format
