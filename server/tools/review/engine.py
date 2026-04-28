"""Review engine orchestrator.

Coordinates the entire automated code review process: computes the diff,
dispatches analyzers, collects findings, filters and prioritizes them,
and posts results to the pull request via the GitHub API.
"""

from __future__ import annotations

from pathlib import Path

from .analyzers.docker_analyzer import DockerAnalyzer
from .analyzers.mypy_analyzer import MypyAnalyzer
from .analyzers.ruff_analyzer import RuffAnalyzer
from .analyzers.security_analyzer import SecurityAnalyzer
from .analyzers.typescript_analyzer import TypeScriptAnalyzer
from .diff import compute_diff_positions, filter_to_diff_lines, git_diff_files
from .dispatcher import AnalyzerDispatcher
from .models import PRContext, ReviewConfig, ReviewResult, Severity
from .prioritize import prioritize_findings
from .reporter import GitHubReporter


def run_review(pr_context: PRContext) -> ReviewResult:
    """Run the full automated code review pipeline for a pull request.

    1. Compute changed files from the diff.
    2. Build a :class:`ReviewConfig` and initialize all analyzers.
    3. Dispatch files to available analyzers via :class:`AnalyzerDispatcher`.
    4. Compute diff mappings and filter findings to diff-visible lines.
    5. Prioritize findings when the count exceeds ``max_comments``.
    6. Post inline review comments and a summary via :class:`GitHubReporter`.

    Args:
        pr_context: Metadata extracted from the GitHub event payload.

    Returns:
        The aggregated :class:`ReviewResult` from all analyzers.
    """
    reporter = GitHubReporter(
        token=pr_context.token,
        repo=f"{pr_context.owner}/{pr_context.repo}",
        pr_number=pr_context.pr_number,
        commit_sha=pr_context.head_sha,
    )

    # Step 1: Compute changed files from the diff
    changed_files = git_diff_files(pr_context.base_sha, pr_context.head_sha)

    if not changed_files:
        empty_result = ReviewResult(findings=[], summary={}, errors=[])
        reporter.post_summary(
            empty_result,
            files_reviewed=0,
            skipped_analyzers=[],
            unmapped_count=0,
        )
        return empty_result

    # Step 2: Build review config
    config = ReviewConfig(
        repo_root=Path.cwd(),
        base_ref=pr_context.base_sha,
        head_ref=pr_context.head_sha,
        changed_files=changed_files,
    )

    # Step 3: Initialize analyzers and dispatch
    analyzers = [
        RuffAnalyzer(),
        MypyAnalyzer(),
        TypeScriptAnalyzer(),
        SecurityAnalyzer(),
        DockerAnalyzer(),
    ]
    available_analyzers = [a for a in analyzers if a.is_available()]
    dispatcher = AnalyzerDispatcher(analyzers=available_analyzers)
    result = dispatcher.dispatch(changed_files, config)

    # Step 4: Compute diff mappings and filter findings to diff lines
    diff_mappings = compute_diff_positions(pr_context.base_sha, pr_context.head_sha)
    visible_findings = filter_to_diff_lines(result.findings, diff_mappings)

    # Step 5: Enforce max comment limit via prioritization
    if len(visible_findings) > config.max_comments:
        visible_findings = prioritize_findings(visible_findings, config.max_comments)

    # Step 6: Post review and summary
    review_result_for_comments = ReviewResult(
        findings=visible_findings,
        summary=result.summary,
        errors=result.errors,
    )
    reporter.post_review(review_result_for_comments, diff_mappings)

    skipped = [a.name for a in analyzers if not a.is_available()]
    unmapped = len(result.findings) - len(visible_findings)
    reporter.post_summary(
        result,
        files_reviewed=len(changed_files),
        skipped_analyzers=skipped,
        unmapped_count=unmapped,
    )

    return result
