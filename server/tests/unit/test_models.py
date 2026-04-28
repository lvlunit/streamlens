"""Unit tests for core data models (Task 1.4).

Tests Severity enum, Finding validation, ReviewConfig defaults,
and ReviewResult initialization.
"""

import pytest

from tools.review.models import (
    Finding,
    ReviewConfig,
    ReviewResult,
    Severity,
)
from pathlib import Path


class TestSeverityEnum:
    """Test Severity enum values and ordering."""

    def test_severity_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_severity_ordering(self):
        """ERROR is most severe, then WARNING, then INFO."""
        severities = [Severity.INFO, Severity.ERROR, Severity.WARNING]
        order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
        sorted_sevs = sorted(severities, key=lambda s: order[s])
        assert sorted_sevs == [Severity.ERROR, Severity.WARNING, Severity.INFO]

    def test_severity_members(self):
        assert len(Severity) == 3
        assert set(Severity) == {Severity.ERROR, Severity.WARNING, Severity.INFO}


class TestFinding:
    """Test Finding construction and validation."""

    def test_valid_finding(self):
        f = Finding(
            file="src/main.py",
            line=10,
            severity=Severity.WARNING,
            message="Unused import",
            analyzer="ruff",
            rule_id="F401",
        )
        assert f.file == "src/main.py"
        assert f.line == 10
        assert f.severity == Severity.WARNING
        assert f.message == "Unused import"
        assert f.analyzer == "ruff"
        assert f.rule_id == "F401"
        assert f.suggestion is None
        assert f.end_line is None

    def test_finding_with_end_line(self):
        f = Finding(
            file="app.ts",
            line=5,
            severity=Severity.ERROR,
            message="Type error",
            analyzer="typescript",
            end_line=8,
        )
        assert f.end_line == 8

    def test_finding_empty_file_raises(self):
        with pytest.raises(ValueError, match="file must be non-empty"):
            Finding(
                file="",
                line=1,
                severity=Severity.ERROR,
                message="msg",
                analyzer="ruff",
            )

    def test_finding_line_less_than_one_raises(self):
        with pytest.raises(ValueError, match="line must be >= 1"):
            Finding(
                file="test.py",
                line=0,
                severity=Severity.ERROR,
                message="msg",
                analyzer="ruff",
            )

    def test_finding_negative_line_raises(self):
        with pytest.raises(ValueError, match="line must be >= 1"):
            Finding(
                file="test.py",
                line=-5,
                severity=Severity.ERROR,
                message="msg",
                analyzer="ruff",
            )

    def test_finding_empty_message_raises(self):
        with pytest.raises(ValueError, match="message must be non-empty"):
            Finding(
                file="test.py",
                line=1,
                severity=Severity.ERROR,
                message="",
                analyzer="ruff",
            )

    def test_finding_end_line_less_than_line_raises(self):
        with pytest.raises(ValueError, match="end_line.*must be >= line"):
            Finding(
                file="test.py",
                line=10,
                severity=Severity.ERROR,
                message="msg",
                analyzer="ruff",
                end_line=5,
            )

    def test_finding_end_line_equal_to_line_ok(self):
        f = Finding(
            file="test.py",
            line=10,
            severity=Severity.ERROR,
            message="msg",
            analyzer="ruff",
            end_line=10,
        )
        assert f.end_line == 10


class TestReviewConfig:
    """Test ReviewConfig defaults."""

    def test_defaults(self):
        config = ReviewConfig(
            repo_root=Path("/repo"),
            base_ref="abc123",
            head_ref="def456",
        )
        assert config.max_comments == 50
        assert config.severity_threshold == Severity.WARNING
        assert config.changed_files == []

    def test_custom_values(self):
        config = ReviewConfig(
            repo_root=Path("/repo"),
            base_ref="abc",
            head_ref="def",
            max_comments=25,
            severity_threshold=Severity.ERROR,
            changed_files=["a.py"],
        )
        assert config.max_comments == 25
        assert config.severity_threshold == Severity.ERROR
        assert config.changed_files == ["a.py"]


class TestReviewResult:
    """Test ReviewResult initialization."""

    def test_empty_defaults(self):
        result = ReviewResult()
        assert result.findings == []
        assert result.summary == {}
        assert result.errors == []

    def test_mutable_defaults_are_independent(self):
        r1 = ReviewResult()
        r2 = ReviewResult()
        r1.findings.append(
            Finding(
                file="a.py",
                line=1,
                severity=Severity.INFO,
                message="test",
                analyzer="ruff",
            )
        )
        assert len(r2.findings) == 0
