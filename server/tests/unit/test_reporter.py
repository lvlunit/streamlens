"""Unit tests for GitHubReporter (Task 8.5).

Tests review comment building, summary formatting, pass/fail status,
retry logic, and fallback behavior.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from tools.review.models import DiffMapping, Finding, ReviewResult, Severity
from tools.review.reporter import GitHubReporter, RateLimitExhausted


def _make_reporter() -> GitHubReporter:
    return GitHubReporter(
        token="test-token",
        repo="owner/repo",
        pr_number=42,
        commit_sha="abc123",
    )


def _make_finding(
    file: str = "test.py",
    line: int = 5,
    severity: Severity = Severity.ERROR,
    message: str = "Test issue",
    analyzer: str = "ruff",
    rule_id: str | None = None,
) -> Finding:
    return Finding(
        file=file,
        line=line,
        severity=severity,
        message=message,
        analyzer=analyzer,
        rule_id=rule_id,
    )


class TestBuildReviewComments:
    """Test _build_review_comments maps findings to correct positions."""

    def test_maps_findings_to_diff_positions(self):
        reporter = _make_reporter()
        findings = [
            _make_finding(file="a.py", line=5),
            _make_finding(file="b.py", line=10),
        ]
        diff_mappings = [
            DiffMapping(file="a.py", line=5, diff_position=3),
            DiffMapping(file="b.py", line=10, diff_position=7),
        ]
        comments = reporter._build_review_comments(findings, diff_mappings)

        assert len(comments) == 2
        assert comments[0]["path"] == "a.py"
        assert comments[0]["position"] == 3
        assert comments[1]["path"] == "b.py"
        assert comments[1]["position"] == 7

    def test_excludes_findings_not_in_diff(self):
        reporter = _make_reporter()
        findings = [
            _make_finding(file="a.py", line=5),
            _make_finding(file="a.py", line=100),  # not in diff
        ]
        diff_mappings = [
            DiffMapping(file="a.py", line=5, diff_position=3),
        ]
        comments = reporter._build_review_comments(findings, diff_mappings)

        assert len(comments) == 1
        assert comments[0]["path"] == "a.py"
        assert comments[0]["position"] == 3

    def test_empty_findings(self):
        reporter = _make_reporter()
        comments = reporter._build_review_comments([], [])
        assert comments == []


class TestFormatSummary:
    """Test _format_summary with various finding distributions."""

    def test_errors_warnings_info(self):
        result = ReviewResult(
            findings=[
                _make_finding(severity=Severity.ERROR, line=1),
                _make_finding(severity=Severity.ERROR, line=2),
                _make_finding(severity=Severity.WARNING, line=3),
                _make_finding(severity=Severity.INFO, line=4),
            ],
            summary={"ruff": 4},
        )
        summary = GitHubReporter._format_summary(
            result, files_reviewed=3, skipped_analyzers=[], unmapped_count=0
        )
        assert "2" in summary  # 2 errors
        assert "1" in summary  # 1 warning, 1 info
        assert "FAIL" in summary  # errors exist

    def test_pass_status_no_errors(self):
        result = ReviewResult(
            findings=[
                _make_finding(severity=Severity.WARNING, line=1),
                _make_finding(severity=Severity.INFO, line=2),
            ],
            summary={"ruff": 2},
        )
        summary = GitHubReporter._format_summary(
            result, files_reviewed=1, skipped_analyzers=[], unmapped_count=0
        )
        assert "PASS" in summary

    def test_fail_status_with_errors(self):
        result = ReviewResult(
            findings=[
                _make_finding(severity=Severity.ERROR, line=1),
            ],
            summary={"ruff": 1},
        )
        summary = GitHubReporter._format_summary(
            result, files_reviewed=1, skipped_analyzers=[], unmapped_count=0
        )
        assert "FAIL" in summary

    def test_empty_findings_pass(self):
        result = ReviewResult(findings=[], summary={})
        summary = GitHubReporter._format_summary(
            result, files_reviewed=0, skipped_analyzers=[], unmapped_count=0
        )
        assert "PASS" in summary

    def test_skipped_analyzers_noted(self):
        result = ReviewResult(findings=[], summary={})
        summary = GitHubReporter._format_summary(
            result, files_reviewed=1, skipped_analyzers=["mypy", "ruff"], unmapped_count=0
        )
        assert "mypy" in summary
        assert "ruff" in summary
        assert "Skipped" in summary


class TestRequestWithRetry:
    """Test _request_with_retry retries on 403 and raises after exhaustion."""

    @patch("tools.review.reporter.time.sleep")
    @patch("tools.review.reporter.httpx.Client")
    def test_retries_on_403_then_succeeds(self, mock_client_cls, mock_sleep):
        """Should retry on 403 and succeed on subsequent 200."""
        reporter = _make_reporter()

        response_403 = MagicMock()
        response_403.status_code = 403

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.request.side_effect = [response_403, response_200]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = reporter._request_with_retry("POST", "https://api.github.com/test")
        assert result.status_code == 200
        assert mock_sleep.call_count == 1

    @patch("tools.review.reporter.time.sleep")
    @patch("tools.review.reporter.httpx.Client")
    def test_raises_rate_limit_exhausted_after_retries(self, mock_client_cls, mock_sleep):
        """Should raise RateLimitExhausted after 3 retries."""
        reporter = _make_reporter()

        response_403 = MagicMock()
        response_403.status_code = 403

        mock_client = MagicMock()
        mock_client.request.return_value = response_403
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(RateLimitExhausted):
            reporter._request_with_retry("POST", "https://api.github.com/test")

        # 3 retries = 3 sleeps (attempts 0,1,2 get 403, sleep after 0,1,2, then attempt 3 = 403 -> raise)
        assert mock_sleep.call_count == 3


class TestPostReviewFallback:
    """Test post_review falls back to summary on RateLimitExhausted."""

    @patch.object(GitHubReporter, "post_summary")
    @patch.object(GitHubReporter, "_request_with_retry")
    def test_falls_back_to_summary_on_rate_limit(self, mock_retry, mock_summary):
        mock_retry.side_effect = RateLimitExhausted("rate limited")

        reporter = _make_reporter()
        result = ReviewResult(
            findings=[_make_finding(line=1)],
            summary={"ruff": 1},
        )
        diff_mappings = [DiffMapping(file="test.py", line=5, diff_position=3)]

        reporter.post_review(result, diff_mappings)

        mock_summary.assert_called_once()
