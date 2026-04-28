"""GitHub PR reporter for posting review findings.

Posts inline review comments and summary comments to pull requests
via the GitHub API using httpx.
"""

from __future__ import annotations

import time

import httpx

from .models import DiffMapping, Finding, ReviewResult, Severity


class RateLimitExhausted(Exception):
    """Raised when all GitHub API retry attempts are exhausted due to rate limiting."""


class GitHubReporter:
    """Posts review findings as inline PR comments via the GitHub API.

    Args:
        token: GitHub API token with ``pull-requests:write`` permission.
        repo: Repository in ``owner/repo`` format.
        pr_number: Pull request number.
        commit_sha: The head commit SHA for the review.
    """

    _BASE_URL = "https://api.github.com"
    _MAX_RETRIES = 3
    _INITIAL_BACKOFF = 5  # seconds

    def __init__(
        self,
        token: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
    ) -> None:
        self._token = token
        self._repo = repo
        self._pr_number = pr_number
        self._commit_sha = commit_sha

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post_review(
        self,
        result: ReviewResult,
        diff_mappings: list[DiffMapping],
    ) -> None:
        """Post findings as a single atomic PR review with inline comments.

        Findings whose lines are not present in *diff_mappings* are
        silently excluded from inline comments.  If a
        :class:`RateLimitExhausted` error occurs, the method falls back
        to posting a summary-only comment instead.

        Args:
            result: Aggregated review result with findings.
            diff_mappings: Mappings from file+line to diff positions.
        """
        comments = self._build_review_comments(result.findings, diff_mappings)

        body = "Automated code review complete."
        if not comments:
            body = "Automated code review complete — no inline findings to report."

        payload: dict = {
            "commit_id": self._commit_sha,
            "body": body,
            "event": "COMMENT",
            "comments": comments,
        }

        url = (
            f"{self._BASE_URL}/repos/{self._repo}"
            f"/pulls/{self._pr_number}/reviews"
        )

        try:
            self._request_with_retry("POST", url, json=payload)
        except RateLimitExhausted:
            # Fall back to a summary-only comment
            unmapped = len(result.findings) - len(comments)
            self.post_summary(
                result,
                files_reviewed=0,
                skipped_analyzers=[],
                unmapped_count=unmapped,
            )

    def post_summary(
        self,
        result: ReviewResult,
        files_reviewed: int,
        skipped_analyzers: list[str],
        unmapped_count: int = 0,
    ) -> None:
        """Post a markdown summary comment on the pull request.

        Args:
            result: Aggregated review result with findings.
            files_reviewed: Number of files that were reviewed.
            skipped_analyzers: Names of analyzers that were skipped.
            unmapped_count: Number of findings that could not be posted
                inline because their lines are outside the diff context.
        """
        body = self._format_summary(
            result, files_reviewed, skipped_analyzers, unmapped_count
        )

        url = (
            f"{self._BASE_URL}/repos/{self._repo}"
            f"/issues/{self._pr_number}/comments"
        )

        try:
            self._request_with_retry("POST", url, json={"body": body})
        except RateLimitExhausted:
            # Nothing more we can do — the summary itself was rate-limited.
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        """Send an HTTP request with exponential backoff on rate limits.

        Retries up to :attr:`_MAX_RETRIES` times when the GitHub API
        returns HTTP 403 (rate limit).  The backoff starts at
        :attr:`_INITIAL_BACKOFF` seconds and doubles each attempt
        (5 → 10 → 20).

        Raises:
            RateLimitExhausted: If all retries are exhausted.
        """
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        backoff = self._INITIAL_BACKOFF

        for attempt in range(self._MAX_RETRIES + 1):
            with httpx.Client() as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,  # type: ignore[arg-type]
                )

            if response.status_code != 403:
                response.raise_for_status()
                return response

            # Rate limited — retry with backoff (except on last attempt)
            if attempt < self._MAX_RETRIES:
                time.sleep(backoff)
                backoff *= 2

        raise RateLimitExhausted(
            f"GitHub API rate limit exceeded after {self._MAX_RETRIES} retries"
        )

    def _build_review_comments(
        self,
        findings: list[Finding],
        diff_mappings: list[DiffMapping],
    ) -> list[dict]:
        """Convert findings to GitHub review comment format.

        Only findings whose ``(file, line)`` pair has a corresponding
        :class:`DiffMapping` are included.

        Returns:
            List of comment dicts suitable for the GitHub review API.
        """
        # Build a lookup: (file, line) -> diff_position
        position_map: dict[tuple[str, int], int] = {}
        for mapping in diff_mappings:
            position_map[(mapping.file, mapping.line)] = mapping.diff_position

        comments: list[dict] = []
        for finding in findings:
            key = (finding.file, finding.line)
            if key not in position_map:
                continue

            severity_icon = _SEVERITY_ICONS.get(finding.severity, "ℹ️")
            body_parts = [f"{severity_icon} **{finding.severity.value.upper()}**"]
            if finding.rule_id:
                body_parts.append(f"(`{finding.rule_id}`)")
            body_parts.append(f": {finding.message}")

            if finding.suggestion:
                body_parts.append(f"\n\n💡 **Suggestion:** {finding.suggestion}")

            comments.append(
                {
                    "path": finding.file,
                    "position": position_map[key],
                    "body": " ".join(body_parts),
                }
            )

        return comments

    @staticmethod
    def _format_summary(
        result: ReviewResult,
        files_reviewed: int,
        skipped_analyzers: list[str],
        unmapped_count: int,
    ) -> str:
        """Build a markdown summary string."""
        # Count by severity
        by_severity: dict[Severity, int] = {
            Severity.ERROR: 0,
            Severity.WARNING: 0,
            Severity.INFO: 0,
        }
        for finding in result.findings:
            by_severity[finding.severity] = (
                by_severity.get(finding.severity, 0) + 1
            )

        error_count = by_severity[Severity.ERROR]
        warning_count = by_severity[Severity.WARNING]
        info_count = by_severity[Severity.INFO]
        total = len(result.findings)

        pass_fail = "✅ **PASS**" if error_count == 0 else "❌ **FAIL**"

        lines = [
            "## Automated Code Review Summary",
            "",
            f"**Status:** {pass_fail}",
            "",
            "### Findings",
            "",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| 🔴 Error | {error_count} |",
            f"| 🟡 Warning | {warning_count} |",
            f"| 🔵 Info | {info_count} |",
            f"| **Total** | **{total}** |",
            "",
        ]

        # Counts by analyzer
        if result.summary:
            lines.append("### By Analyzer")
            lines.append("")
            lines.append("| Analyzer | Findings |")
            lines.append("|----------|----------|")
            for analyzer_name, count in sorted(result.summary.items()):
                lines.append(f"| {analyzer_name} | {count} |")
            lines.append("")

        lines.append(f"**Files reviewed:** {files_reviewed}")
        lines.append("")

        if unmapped_count > 0:
            lines.append(
                f"ℹ️ {unmapped_count} finding(s) could not be posted inline "
                f"(lines outside diff context)."
            )
            lines.append("")

        if skipped_analyzers:
            skipped_str = ", ".join(skipped_analyzers)
            lines.append(
                f"⚠️ Skipped analyzers (tool not available): {skipped_str}"
            )
            lines.append("")

        return "\n".join(lines)


_SEVERITY_ICONS: dict[Severity, str] = {
    Severity.ERROR: "🔴",
    Severity.WARNING: "🟡",
    Severity.INFO: "🔵",
}
