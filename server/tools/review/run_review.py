"""CLI entry point for the automated code review engine.

Reads GitHub event metadata from environment variables, constructs a
:class:`PRContext`, runs the review pipeline, and exits with code 1
if any ERROR-severity findings are detected.

Usage (from GitHub Actions)::

    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    run: python server/tools/review/run_review.py
"""

from __future__ import annotations

import json
import os
import sys

from .engine import run_review
from .models import PRContext, Severity


def main() -> None:
    """Parse environment and event payload, then run the review."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("ERROR: GITHUB_EVENT_PATH environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(event_path) as f:
            event = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: Failed to read event payload from {event_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        pr_context = PRContext(
            owner=event["repository"]["owner"]["login"],
            repo=event["repository"]["name"],
            pr_number=event["pull_request"]["number"],
            base_sha=event["pull_request"]["base"]["sha"],
            head_sha=event["pull_request"]["head"]["sha"],
            token=token,
        )
    except (KeyError, TypeError) as exc:
        print(f"ERROR: Failed to parse PR context from event payload: {exc}", file=sys.stderr)
        sys.exit(1)

    result = run_review(pr_context)

    # Exit with code 1 only if ERROR-severity findings exist on changed lines.
    # Pre-existing issues outside the diff should not block PRs.
    from tools.review.diff import compute_diff_positions, filter_to_diff_lines

    diff_mappings = compute_diff_positions(pr_context.base_sha, pr_context.head_sha)
    visible_findings = filter_to_diff_lines(result.findings, diff_mappings)
    error_count = sum(1 for f in visible_findings if f.severity == Severity.ERROR)
    if error_count > 0:
        print(f"Review complete: {error_count} error(s) found on changed lines.", file=sys.stderr)
        sys.exit(1)

    print("Review complete: no errors on changed lines.")


if __name__ == "__main__":
    main()
