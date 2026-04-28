"""Unit tests for the review engine orchestrator (Task 9.4).

Tests run_review flow with mocked dependencies, empty changed files,
max_comments enforcement, and error aggregation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.review.engine import run_review
from tools.review.models import (
    DiffMapping,
    Finding,
    PRContext,
    ReviewResult,
    Severity,
)


def _make_pr_context() -> PRContext:
    return PRContext(
        owner="testowner",
        repo="testrepo",
        pr_number=1,
        base_sha="base123",
        head_sha="head456",
        token="ghp_testtoken",
    )


def _make_finding(
    file: str = "test.py",
    line: int = 1,
    severity: Severity = Severity.WARNING,
    analyzer: str = "ruff",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        severity=severity,
        message=f"Issue at {file}:{line}",
        analyzer=analyzer,
    )


class TestRunReview:
    """Test full run_review flow with mocked components."""

    @patch("tools.review.engine.GitHubReporter")
    @patch("tools.review.engine.AnalyzerDispatcher")
    @patch("tools.review.engine.compute_diff_positions")
    @patch("tools.review.engine.filter_to_diff_lines")
    @patch("tools.review.engine.git_diff_files")
    @patch("tools.review.engine.RuffAnalyzer")
    @patch("tools.review.engine.MypyAnalyzer")
    @patch("tools.review.engine.TypeScriptAnalyzer")
    @patch("tools.review.engine.SecurityAnalyzer")
    @patch("tools.review.engine.DockerAnalyzer")
    def test_full_flow(
        self,
        mock_docker,
        mock_security,
        mock_ts,
        mock_mypy,
        mock_ruff,
        mock_git_diff,
        mock_filter,
        mock_compute,
        mock_dispatcher_cls,
        mock_reporter_cls,
    ):
        # Setup
        mock_git_diff.return_value = ["main.py", "app.ts"]

        findings = [_make_finding("main.py", 5)]
        mock_dispatch_result = ReviewResult(
            findings=findings, summary={"ruff": 1}, errors=[]
        )
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = mock_dispatch_result
        mock_dispatcher_cls.return_value = mock_dispatcher

        diff_mappings = [DiffMapping(file="main.py", line=5, diff_position=3)]
        mock_compute.return_value = diff_mappings
        mock_filter.return_value = findings

        mock_reporter = MagicMock()
        mock_reporter_cls.return_value = mock_reporter

        # Make all analyzers available
        for mock_analyzer in [mock_ruff, mock_mypy, mock_ts, mock_security, mock_docker]:
            mock_analyzer.return_value.is_available.return_value = True

        # Execute
        result = run_review(_make_pr_context())

        # Verify
        mock_git_diff.assert_called_once()
        mock_dispatcher.dispatch.assert_called_once()
        mock_reporter.post_review.assert_called_once()
        mock_reporter.post_summary.assert_called_once()
        assert len(result.findings) == 1

    @patch("tools.review.engine.GitHubReporter")
    @patch("tools.review.engine.git_diff_files")
    def test_empty_changed_files(self, mock_git_diff, mock_reporter_cls):
        """When no files changed, should post summary and return empty result."""
        mock_git_diff.return_value = []
        mock_reporter = MagicMock()
        mock_reporter_cls.return_value = mock_reporter

        result = run_review(_make_pr_context())

        assert result.findings == []
        assert result.summary == {}
        mock_reporter.post_summary.assert_called_once()

    @patch("tools.review.engine.GitHubReporter")
    @patch("tools.review.engine.AnalyzerDispatcher")
    @patch("tools.review.engine.compute_diff_positions")
    @patch("tools.review.engine.filter_to_diff_lines")
    @patch("tools.review.engine.git_diff_files")
    @patch("tools.review.engine.prioritize_findings")
    @patch("tools.review.engine.RuffAnalyzer")
    @patch("tools.review.engine.MypyAnalyzer")
    @patch("tools.review.engine.TypeScriptAnalyzer")
    @patch("tools.review.engine.SecurityAnalyzer")
    @patch("tools.review.engine.DockerAnalyzer")
    def test_max_comments_enforcement(
        self,
        mock_docker,
        mock_security,
        mock_ts,
        mock_mypy,
        mock_ruff,
        mock_prioritize,
        mock_git_diff,
        mock_filter,
        mock_compute,
        mock_dispatcher_cls,
        mock_reporter_cls,
    ):
        """When findings exceed max_comments, prioritize_findings is called."""
        mock_git_diff.return_value = ["main.py"]

        # Generate more than 50 findings
        many_findings = [_make_finding("main.py", i) for i in range(1, 60)]
        mock_dispatch_result = ReviewResult(
            findings=many_findings, summary={"ruff": 59}, errors=[]
        )
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = mock_dispatch_result
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_compute.return_value = [
            DiffMapping(file="main.py", line=i, diff_position=i) for i in range(1, 60)
        ]
        mock_filter.return_value = many_findings

        prioritized = many_findings[:50]
        mock_prioritize.return_value = prioritized

        mock_reporter = MagicMock()
        mock_reporter_cls.return_value = mock_reporter

        for mock_analyzer in [mock_ruff, mock_mypy, mock_ts, mock_security, mock_docker]:
            mock_analyzer.return_value.is_available.return_value = True

        run_review(_make_pr_context())

        mock_prioritize.assert_called_once_with(many_findings, 50)

    @patch("tools.review.engine.GitHubReporter")
    @patch("tools.review.engine.AnalyzerDispatcher")
    @patch("tools.review.engine.compute_diff_positions")
    @patch("tools.review.engine.filter_to_diff_lines")
    @patch("tools.review.engine.git_diff_files")
    @patch("tools.review.engine.RuffAnalyzer")
    @patch("tools.review.engine.MypyAnalyzer")
    @patch("tools.review.engine.TypeScriptAnalyzer")
    @patch("tools.review.engine.SecurityAnalyzer")
    @patch("tools.review.engine.DockerAnalyzer")
    def test_error_aggregation(
        self,
        mock_docker,
        mock_security,
        mock_ts,
        mock_mypy,
        mock_ruff,
        mock_git_diff,
        mock_filter,
        mock_compute,
        mock_dispatcher_cls,
        mock_reporter_cls,
    ):
        """Errors from failed analyzers should be in the result."""
        mock_git_diff.return_value = ["main.py"]

        mock_dispatch_result = ReviewResult(
            findings=[],
            summary={},
            errors=["Analyzer 'ruff' failed: tool crashed"],
        )
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = mock_dispatch_result
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_compute.return_value = []
        mock_filter.return_value = []

        mock_reporter = MagicMock()
        mock_reporter_cls.return_value = mock_reporter

        for mock_analyzer in [mock_ruff, mock_mypy, mock_ts, mock_security, mock_docker]:
            mock_analyzer.return_value.is_available.return_value = True

        result = run_review(_make_pr_context())

        assert len(result.errors) == 1
        assert "ruff" in result.errors[0]
