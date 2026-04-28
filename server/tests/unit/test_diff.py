"""Unit tests for diff computation and position mapping (Task 2.7).

Tests git_diff_files, compute_diff_positions, filter_to_diff_lines,
and _validate_file_path.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.review.diff import (
    _validate_file_path,
    compute_diff_positions,
    filter_to_diff_lines,
    git_diff_files,
)
from tools.review.models import DiffMapping, Finding, Severity


class TestGitDiffFiles:
    """Test git_diff_files with mocked subprocess."""

    @patch("tools.review.diff.subprocess.run")
    def test_returns_added_and_modified_files(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="src/main.py\nREADME.md\nserver/app.ts\n",
            returncode=0,
        )
        result = git_diff_files("base123", "head456")
        assert result == ["src/main.py", "README.md", "server/app.ts"]
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--diff-filter=d" in cmd
        assert "base123...head456" in cmd

    @patch("tools.review.diff.subprocess.run")
    def test_empty_diff_returns_empty_list(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = git_diff_files("base", "head")
        assert result == []

    @patch("tools.review.diff.subprocess.run")
    def test_raises_on_traversal_path(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="../etc/passwd\n",
            returncode=0,
        )
        with pytest.raises(ValueError, match="Unsafe file path"):
            git_diff_files("base", "head")

    @patch("tools.review.diff.subprocess.run")
    def test_raises_on_absolute_path(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="/etc/passwd\n",
            returncode=0,
        )
        with pytest.raises(ValueError, match="Unsafe file path"):
            git_diff_files("base", "head")


class TestComputeDiffPositions:
    """Test compute_diff_positions with sample unified diffs."""

    @patch("tools.review.diff.subprocess.run")
    def test_single_hunk(self, mock_run):
        diff_output = (
            "diff --git a/test.py b/test.py\n"
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+added_line\n"
            " line2\n"
            " line3\n"
        )
        mock_run.return_value = MagicMock(stdout=diff_output, returncode=0)
        mappings = compute_diff_positions("base", "head")

        assert len(mappings) == 1
        assert mappings[0].file == "test.py"
        assert mappings[0].line == 2  # new-file line 2 (after context line1 at line 1)
        assert mappings[0].diff_position >= 1  # 1-based position

    @patch("tools.review.diff.subprocess.run")
    def test_multi_hunk(self, mock_run):
        diff_output = (
            "diff --git a/test.py b/test.py\n"
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+first_add\n"
            " line2\n"
            " line3\n"
            "@@ -10,3 +11,4 @@\n"
            " line10\n"
            "+second_add\n"
            " line11\n"
            " line12\n"
        )
        mock_run.return_value = MagicMock(stdout=diff_output, returncode=0)
        mappings = compute_diff_positions("base", "head")

        assert len(mappings) == 2
        # First hunk addition
        assert mappings[0].file == "test.py"
        assert mappings[0].line == 2
        # Second hunk addition
        assert mappings[1].file == "test.py"
        assert mappings[1].line == 12

    @patch("tools.review.diff.subprocess.run")
    def test_multi_file(self, mock_run):
        diff_output = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,3 @@\n"
            " existing\n"
            "+new_in_a\n"
            " end\n"
            "diff --git a/b.ts b/b.ts\n"
            "--- a/b.ts\n"
            "+++ b/b.ts\n"
            "@@ -1,2 +1,3 @@\n"
            " existing\n"
            "+new_in_b\n"
            " end\n"
        )
        mock_run.return_value = MagicMock(stdout=diff_output, returncode=0)
        mappings = compute_diff_positions("base", "head")

        assert len(mappings) == 2
        files = {m.file for m in mappings}
        assert files == {"a.py", "b.ts"}
        assert mappings[0].file == "a.py"
        assert mappings[1].file == "b.ts"


class TestFilterToDiffLines:
    """Test filter_to_diff_lines with findings on and off diff lines."""

    def test_keeps_findings_on_diff_lines(self):
        findings = [
            Finding(file="a.py", line=5, severity=Severity.ERROR, message="err", analyzer="ruff"),
            Finding(file="a.py", line=10, severity=Severity.WARNING, message="warn", analyzer="ruff"),
        ]
        diff_mappings = [
            DiffMapping(file="a.py", line=5, diff_position=3),
        ]
        result = filter_to_diff_lines(findings, diff_mappings)
        assert len(result) == 1
        assert result[0].line == 5

    def test_excludes_findings_off_diff_lines(self):
        findings = [
            Finding(file="a.py", line=100, severity=Severity.ERROR, message="err", analyzer="ruff"),
        ]
        diff_mappings = [
            DiffMapping(file="a.py", line=5, diff_position=3),
        ]
        result = filter_to_diff_lines(findings, diff_mappings)
        assert len(result) == 0

    def test_preserves_order(self):
        findings = [
            Finding(file="a.py", line=10, severity=Severity.ERROR, message="second", analyzer="ruff"),
            Finding(file="a.py", line=5, severity=Severity.WARNING, message="first", analyzer="ruff"),
        ]
        diff_mappings = [
            DiffMapping(file="a.py", line=10, diff_position=5),
            DiffMapping(file="a.py", line=5, diff_position=2),
        ]
        result = filter_to_diff_lines(findings, diff_mappings)
        assert len(result) == 2
        assert result[0].message == "second"
        assert result[1].message == "first"

    def test_empty_findings(self):
        result = filter_to_diff_lines([], [DiffMapping(file="a.py", line=1, diff_position=1)])
        assert result == []

    def test_empty_diff_mappings(self):
        findings = [
            Finding(file="a.py", line=1, severity=Severity.ERROR, message="err", analyzer="ruff"),
        ]
        result = filter_to_diff_lines(findings, [])
        assert result == []


class TestValidateFilePath:
    """Test _validate_file_path rejects unsafe paths."""

    def test_valid_relative_path(self):
        assert _validate_file_path("src/main.py") is True

    def test_valid_simple_filename(self):
        assert _validate_file_path("README.md") is True

    def test_rejects_traversal(self):
        assert _validate_file_path("../etc/passwd") is False

    def test_rejects_mid_traversal(self):
        assert _validate_file_path("src/../../../etc/passwd") is False

    def test_rejects_absolute_path(self):
        assert _validate_file_path("/etc/passwd") is False

    def test_rejects_empty_path(self):
        assert _validate_file_path("") is False
