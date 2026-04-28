"""Unit tests for finding prioritization (Task 3.5).

Tests severity ordering, security analyzer priority, count enforcement,
and no-truncation behavior.
"""

from tools.review.models import Finding, Severity
from tools.review.prioritize import prioritize_findings


def _make_finding(severity: Severity, analyzer: str = "ruff", line: int = 1) -> Finding:
    return Finding(
        file="test.py",
        line=line,
        severity=severity,
        message=f"{severity.value} from {analyzer}",
        analyzer=analyzer,
    )


class TestPrioritizeFindings:
    """Test prioritize_findings behavior."""

    def test_mixed_severity_errors_first(self):
        """With max_comments=3, should get ERRORs first."""
        findings = [
            _make_finding(Severity.INFO, "ruff", line=1),
            _make_finding(Severity.ERROR, "ruff", line=2),
            _make_finding(Severity.WARNING, "ruff", line=3),
            _make_finding(Severity.ERROR, "mypy", line=4),
            _make_finding(Severity.INFO, "ruff", line=5),
        ]
        result = prioritize_findings(findings, max_count=3)
        assert len(result) == 3
        # First two should be ERROR severity
        assert result[0].severity == Severity.ERROR
        assert result[1].severity == Severity.ERROR
        # Third should be WARNING
        assert result[2].severity == Severity.WARNING

    def test_security_priority_within_same_severity(self):
        """Security findings should come before other analyzers at same severity."""
        findings = [
            _make_finding(Severity.ERROR, "ruff", line=1),
            _make_finding(Severity.ERROR, "security", line=2),
            _make_finding(Severity.ERROR, "mypy", line=3),
        ]
        result = prioritize_findings(findings, max_count=3)
        assert result[0].analyzer == "security"
        assert result[1].analyzer in ("ruff", "mypy")

    def test_exact_count_enforcement(self):
        """Output length should equal max_count."""
        findings = [_make_finding(Severity.WARNING, line=i) for i in range(1, 11)]
        result = prioritize_findings(findings, max_count=5)
        assert len(result) == 5

    def test_fewer_findings_than_max_no_truncation(self):
        """When fewer findings than max_comments, all should be returned."""
        findings = [
            _make_finding(Severity.ERROR, line=1),
            _make_finding(Severity.WARNING, line=2),
        ]
        result = prioritize_findings(findings, max_count=10)
        assert len(result) == 2

    def test_empty_findings(self):
        result = prioritize_findings([], max_count=5)
        assert result == []

    def test_severity_ordering_complete(self):
        """Full ordering: ERROR > WARNING > INFO."""
        findings = [
            _make_finding(Severity.INFO, line=1),
            _make_finding(Severity.WARNING, line=2),
            _make_finding(Severity.ERROR, line=3),
        ]
        result = prioritize_findings(findings, max_count=3)
        assert result[0].severity == Severity.ERROR
        assert result[1].severity == Severity.WARNING
        assert result[2].severity == Severity.INFO
