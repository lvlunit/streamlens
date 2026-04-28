"""Finding prioritization for the automated code review engine.

Sorts and truncates findings so that the most critical issues are
reported first when the total count exceeds the configured limit.
"""

from __future__ import annotations

from .models import Finding, Severity


def prioritize_findings(findings: list[Finding], max_count: int) -> list[Finding]:
    """Select the most important findings up to *max_count*.

    Findings are sorted by severity (ERROR > WARNING > INFO), then by
    analyzer priority (security first, then linters, then other tools).
    The sort is stable, so relative order within each priority group is
    preserved.  The result is truncated to exactly *max_count* entries.

    Args:
        findings: All candidate findings.
        max_count: Maximum number of findings to return.

    Returns:
        A list of at most *max_count* findings, ordered by priority.
    """
    severity_order: dict[Severity, int] = {
        Severity.ERROR: 0,
        Severity.WARNING: 1,
        Severity.INFO: 2,
    }
    analyzer_priority: dict[str, int] = {
        "security": 0,
        "ruff": 1,
        "mypy": 1,
        "typescript": 1,
        "docker": 2,
    }

    sorted_findings = sorted(
        findings,
        key=lambda f: (
            severity_order.get(f.severity, 3),
            analyzer_priority.get(f.analyzer, 3),
        ),
    )

    return sorted_findings[:max_count]
