"""Unit tests for concrete analyzers (Task 6.7).

Tests RuffAnalyzer, MypyAnalyzer, TypeScriptAnalyzer, SecurityAnalyzer,
DockerAnalyzer with mocked subprocess calls and known tool output.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.review.analyzers.docker_analyzer import DockerAnalyzer
from tools.review.analyzers.mypy_analyzer import MypyAnalyzer
from tools.review.analyzers.ruff_analyzer import RuffAnalyzer
from tools.review.analyzers.security_analyzer import SecurityAnalyzer
from tools.review.analyzers.typescript_analyzer import TypeScriptAnalyzer
from tools.review.models import ReviewConfig, Severity


def _make_config() -> ReviewConfig:
    return ReviewConfig(
        repo_root=Path("/repo"),
        base_ref="base",
        head_ref="head",
    )


# ── RuffAnalyzer ──────────────────────────────────────────────────────


class TestRuffAnalyzer:
    """Test RuffAnalyzer with mocked subprocess."""

    @patch("tools.review.analyzers.ruff_analyzer.subprocess.run")
    def test_parses_json_output(self, mock_run):
        ruff_output = json.dumps([
            {
                "code": "E501",
                "message": "Line too long",
                "filename": "test.py",
                "location": {"row": 10, "column": 1},
                "end_location": {"row": 10, "column": 90},
            }
        ])
        mock_run.return_value = MagicMock(stdout=ruff_output, returncode=1)

        analyzer = RuffAnalyzer()
        findings = analyzer.analyze(["test.py"], _make_config())

        assert len(findings) == 1
        assert findings[0].file == "test.py"
        assert findings[0].line == 10
        assert findings[0].message == "Line too long"
        assert findings[0].rule_id == "E501"
        assert findings[0].severity == Severity.ERROR  # E-codes map to ERROR

    @patch("tools.review.analyzers.ruff_analyzer.subprocess.run")
    def test_empty_output_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        analyzer = RuffAnalyzer()
        findings = analyzer.analyze(["test.py"], _make_config())
        assert findings == []

    @patch("tools.review.analyzers.ruff_analyzer.subprocess.run")
    def test_warning_severity_mapping(self, mock_run):
        ruff_output = json.dumps([
            {
                "code": "W291",
                "message": "Trailing whitespace",
                "filename": "test.py",
                "location": {"row": 5, "column": 1},
                "end_location": {"row": 5, "column": 10},
            }
        ])
        mock_run.return_value = MagicMock(stdout=ruff_output, returncode=1)
        analyzer = RuffAnalyzer()
        findings = analyzer.analyze(["test.py"], _make_config())
        assert findings[0].severity == Severity.WARNING

    @patch("tools.review.analyzers.ruff_analyzer.subprocess.run")
    def test_is_available_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        analyzer = RuffAnalyzer()
        assert analyzer.is_available() is True

    @patch("tools.review.analyzers.ruff_analyzer.subprocess.run")
    def test_is_available_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        analyzer = RuffAnalyzer()
        assert analyzer.is_available() is False


# ── MypyAnalyzer ──────────────────────────────────────────────────────


class TestMypyAnalyzer:
    """Test MypyAnalyzer with mocked subprocess."""

    @patch("tools.review.analyzers.mypy_analyzer.subprocess.run")
    def test_parses_output(self, mock_run):
        mypy_output = (
            "test.py:5:1: error: Incompatible types\n"
            "test.py:10:1: note: See above\n"
        )
        mock_run.return_value = MagicMock(stdout=mypy_output, returncode=1)

        analyzer = MypyAnalyzer()
        findings = analyzer.analyze(["test.py"], _make_config())

        assert len(findings) == 2
        assert findings[0].file == "test.py"
        assert findings[0].line == 5
        assert findings[0].severity == Severity.ERROR
        assert findings[0].message == "Incompatible types"
        # note maps to INFO
        assert findings[1].severity == Severity.INFO
        assert findings[1].line == 10

    @patch("tools.review.analyzers.mypy_analyzer.subprocess.run")
    def test_empty_output_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        analyzer = MypyAnalyzer()
        findings = analyzer.analyze(["test.py"], _make_config())
        assert findings == []

    @patch("tools.review.analyzers.mypy_analyzer.subprocess.run")
    def test_is_available_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        analyzer = MypyAnalyzer()
        assert analyzer.is_available() is True

    @patch("tools.review.analyzers.mypy_analyzer.subprocess.run")
    def test_is_available_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        analyzer = MypyAnalyzer()
        assert analyzer.is_available() is False


# ── TypeScriptAnalyzer ────────────────────────────────────────────────


class TestTypeScriptAnalyzer:
    """Test TypeScriptAnalyzer with mocked subprocess."""

    @patch("tools.review.analyzers.typescript_analyzer.subprocess.run")
    def test_parses_tsc_output(self, mock_run):
        tsc_output = "app.ts(3,5): error TS2345: Argument of type 'string' is not assignable"
        mock_run.return_value = MagicMock(stdout=tsc_output, returncode=1)

        analyzer = TypeScriptAnalyzer()
        findings = analyzer.analyze(["app.ts"], _make_config())

        assert len(findings) == 1
        assert findings[0].file == "app.ts"
        assert findings[0].line == 3
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule_id == "TS2345"
        assert "Argument of type" in findings[0].message

    @patch("tools.review.analyzers.typescript_analyzer.subprocess.run")
    def test_filters_to_changed_files_only(self, mock_run):
        tsc_output = (
            "app.ts(3,5): error TS2345: Type error\n"
            "other.ts(10,1): error TS1234: Another error\n"
        )
        mock_run.return_value = MagicMock(stdout=tsc_output, returncode=1)

        analyzer = TypeScriptAnalyzer()
        # Only app.ts is in the changed files
        findings = analyzer.analyze(["app.ts"], _make_config())

        assert len(findings) == 1
        assert findings[0].file == "app.ts"

    @patch("tools.review.analyzers.typescript_analyzer.subprocess.run")
    def test_empty_output_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        analyzer = TypeScriptAnalyzer()
        findings = analyzer.analyze(["app.ts"], _make_config())
        assert findings == []

    @patch("tools.review.analyzers.typescript_analyzer.subprocess.run")
    def test_is_available_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        analyzer = TypeScriptAnalyzer()
        assert analyzer.is_available() is True

    @patch("tools.review.analyzers.typescript_analyzer.subprocess.run")
    def test_is_available_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        analyzer = TypeScriptAnalyzer()
        assert analyzer.is_available() is False


# ── SecurityAnalyzer ──────────────────────────────────────────────────


class TestSecurityAnalyzer:
    """Test SecurityAnalyzer bandit output parsing."""

    @patch.object(SecurityAnalyzer, "_check_tool", return_value=True)
    @patch("tools.review.analyzers.security_analyzer.subprocess.run")
    def test_parses_bandit_json(self, mock_run, mock_check):
        bandit_output = json.dumps({
            "results": [
                {
                    "filename": "app.py",
                    "line_number": 15,
                    "issue_severity": "HIGH",
                    "issue_text": "Use of exec detected",
                    "test_id": "B102",
                }
            ]
        })
        # First call is bandit, second would be trivy (empty)
        mock_run.side_effect = [
            MagicMock(stdout=bandit_output, returncode=1),
            MagicMock(stdout="", returncode=0),
        ]

        analyzer = SecurityAnalyzer()
        findings = analyzer.analyze(["app.py"], _make_config())

        bandit_findings = [f for f in findings if f.rule_id == "B102"]
        assert len(bandit_findings) == 1
        assert bandit_findings[0].file == "app.py"
        assert bandit_findings[0].line == 15
        assert bandit_findings[0].severity == Severity.ERROR  # HIGH -> ERROR
        assert bandit_findings[0].message == "Use of exec detected"

    @patch.object(SecurityAnalyzer, "_check_tool")
    def test_is_available_with_bandit_only(self, mock_check):
        mock_check.side_effect = lambda tool: tool == "bandit"
        analyzer = SecurityAnalyzer()
        assert analyzer.is_available() is True

    @patch.object(SecurityAnalyzer, "_check_tool", return_value=False)
    def test_is_available_neither_tool(self, mock_check):
        analyzer = SecurityAnalyzer()
        assert analyzer.is_available() is False


# ── DockerAnalyzer ────────────────────────────────────────────────────


class TestDockerAnalyzer:
    """Test DockerAnalyzer hadolint output parsing and Dockerfile matching."""

    @patch("tools.review.analyzers.docker_analyzer.subprocess.run")
    def test_parses_hadolint_json(self, mock_run):
        hadolint_output = json.dumps([
            {
                "file": "Dockerfile",
                "line": 3,
                "level": "warning",
                "message": "Pin versions in apt-get install",
                "code": "DL3008",
            }
        ])
        mock_run.return_value = MagicMock(stdout=hadolint_output, returncode=1)

        analyzer = DockerAnalyzer()
        findings = analyzer.analyze(["Dockerfile"], _make_config())

        assert len(findings) == 1
        assert findings[0].file == "Dockerfile"
        assert findings[0].line == 3
        assert findings[0].severity == Severity.WARNING
        assert findings[0].rule_id == "DL3008"

    def test_match_dockerfiles_matches_dockerfile(self):
        files = ["Dockerfile", "src/main.py", "build.dockerfile", "README.md"]
        matched = DockerAnalyzer._match_dockerfiles(files)
        assert "Dockerfile" in matched
        assert "build.dockerfile" in matched
        assert "src/main.py" not in matched
        assert "README.md" not in matched

    def test_match_dockerfiles_case_sensitive(self):
        """Only exact 'Dockerfile' basename matches, not 'dockerfile'."""
        files = ["dockerfile", "Dockerfile"]
        matched = DockerAnalyzer._match_dockerfiles(files)
        assert "Dockerfile" in matched
        # 'dockerfile' has no extension match and basename != 'Dockerfile'
        assert "dockerfile" not in matched

    @patch("tools.review.analyzers.docker_analyzer.subprocess.run")
    def test_is_available_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        analyzer = DockerAnalyzer()
        assert analyzer.is_available() is True

    @patch("tools.review.analyzers.docker_analyzer.subprocess.run")
    def test_is_available_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        analyzer = DockerAnalyzer()
        assert analyzer.is_available() is False
