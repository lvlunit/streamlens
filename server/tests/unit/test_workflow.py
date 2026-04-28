"""Unit tests for GitHub Actions workflow configuration (Task 10.3).

Reads and validates the code-review.yml workflow file for correct
permissions, triggers, and checkout configuration.
"""

from pathlib import Path

import yaml
import pytest


WORKFLOW_PATH = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "code-review.yml"


@pytest.fixture
def workflow():
    """Load and parse the workflow YAML."""
    assert WORKFLOW_PATH.exists(), f"Workflow file not found: {WORKFLOW_PATH}"
    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


class TestWorkflowPermissions:
    """Validate workflow permissions."""

    def test_has_contents_read(self, workflow):
        permissions = workflow.get("permissions", {})
        assert permissions.get("contents") == "read"

    def test_has_pull_requests_write(self, workflow):
        permissions = workflow.get("permissions", {})
        assert permissions.get("pull-requests") == "write"


class TestWorkflowTriggers:
    """Validate workflow triggers on pull_request events."""

    def test_triggers_on_pull_request(self, workflow):
        triggers = workflow.get("on", workflow.get(True, {}))
        assert "pull_request" in triggers


class TestWorkflowCheckout:
    """Validate checkout step has fetch-depth: 0."""

    def test_checkout_has_fetch_depth_zero(self, workflow):
        jobs = workflow.get("jobs", {})
        review_job = jobs.get("review", {})
        steps = review_job.get("steps", [])

        checkout_step = None
        for step in steps:
            uses = step.get("uses", "")
            if "actions/checkout" in uses:
                checkout_step = step
                break

        assert checkout_step is not None, "No checkout step found"
        with_config = checkout_step.get("with", {})
        assert with_config.get("fetch-depth") == 0
