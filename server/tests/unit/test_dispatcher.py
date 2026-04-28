"""Unit tests for AnalyzerDispatcher (Task 5.7).

Tests routing, availability filtering, error handling, empty file lists,
and per-analyzer summary counts.
"""

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

from tools.review.dispatcher import AnalyzerDispatcher
from tools.review.models import Finding, ReviewConfig, ReviewResult, Severity


def _make_config() -> ReviewConfig:
    return ReviewConfig(
        repo_root=Path("/repo"),
        base_ref="base",
        head_ref="head",
    )


def _make_analyzer(
    name: str,
    extensions: set[str],
    available: bool = True,
    findings: list[Finding] | None = None,
    raises: Exception | None = None,
) -> MagicMock:
    """Create a mock analyzer with configurable behavior."""
    analyzer = MagicMock()
    type(analyzer).name = PropertyMock(return_value=name)
    type(analyzer).supported_extensions = PropertyMock(return_value=extensions)
    analyzer.is_available.return_value = available

    if raises:
        analyzer.analyze.side_effect = raises
    elif findings is not None:
        analyzer.analyze.return_value = findings
    else:
        analyzer.analyze.return_value = []

    return analyzer


class TestAnalyzerDispatcher:
    """Test AnalyzerDispatcher routing and aggregation."""

    def test_routes_files_to_matching_analyzers(self):
        """Python files go to py analyzer, TS files go to ts analyzer."""
        py_finding = Finding(
            file="main.py", line=1, severity=Severity.ERROR,
            message="py issue", analyzer="ruff",
        )
        ts_finding = Finding(
            file="app.ts", line=1, severity=Severity.WARNING,
            message="ts issue", analyzer="typescript",
        )
        py_analyzer = _make_analyzer("ruff", {".py"}, findings=[py_finding])
        ts_analyzer = _make_analyzer("typescript", {".ts"}, findings=[ts_finding])

        dispatcher = AnalyzerDispatcher([py_analyzer, ts_analyzer])
        result = dispatcher.dispatch(["main.py", "app.ts"], _make_config())

        assert len(result.findings) == 2
        py_analyzer.analyze.assert_called_once()
        ts_analyzer.analyze.assert_called_once()
        # Verify correct files were passed
        py_call_files = py_analyzer.analyze.call_args[0][0]
        ts_call_files = ts_analyzer.analyze.call_args[0][0]
        assert py_call_files == ["main.py"]
        assert ts_call_files == ["app.ts"]

    def test_skips_unavailable_analyzers(self):
        """Unavailable analyzers should be skipped."""
        available = _make_analyzer("ruff", {".py"}, available=True, findings=[])
        unavailable = _make_analyzer("mypy", {".py"}, available=False)

        dispatcher = AnalyzerDispatcher([available, unavailable])
        result = dispatcher.dispatch(["test.py"], _make_config())

        available.analyze.assert_called_once()
        unavailable.analyze.assert_not_called()
        # Skipped analyzer should be noted in errors
        assert any("skipped" in e.lower() for e in result.errors)

    def test_error_handling_on_analyzer_exception(self):
        """When an analyzer raises RuntimeError, error is captured and others continue."""
        failing = _make_analyzer(
            "ruff", {".py"}, raises=RuntimeError("ruff crashed")
        )
        working_finding = Finding(
            file="test.py", line=1, severity=Severity.INFO,
            message="ok", analyzer="mypy",
        )
        working = _make_analyzer("mypy", {".py"}, findings=[working_finding])

        dispatcher = AnalyzerDispatcher([failing, working])
        result = dispatcher.dispatch(["test.py"], _make_config())

        assert len(result.findings) == 1
        assert result.findings[0].analyzer == "mypy"
        assert any("ruff" in e and "failed" in e for e in result.errors)

    def test_empty_file_list_analyzer_not_called(self):
        """Analyzer should not be called when no files match its extensions."""
        py_analyzer = _make_analyzer("ruff", {".py"})

        dispatcher = AnalyzerDispatcher([py_analyzer])
        result = dispatcher.dispatch(["app.ts", "style.css"], _make_config())

        py_analyzer.analyze.assert_not_called()
        assert len(result.findings) == 0

    def test_per_analyzer_summary_counts(self):
        """Summary should accurately count findings per analyzer."""
        findings_a = [
            Finding(file="a.py", line=1, severity=Severity.ERROR, message="e1", analyzer="ruff"),
            Finding(file="a.py", line=2, severity=Severity.WARNING, message="e2", analyzer="ruff"),
        ]
        findings_b = [
            Finding(file="a.py", line=3, severity=Severity.INFO, message="e3", analyzer="mypy"),
        ]
        analyzer_a = _make_analyzer("ruff", {".py"}, findings=findings_a)
        analyzer_b = _make_analyzer("mypy", {".py"}, findings=findings_b)

        dispatcher = AnalyzerDispatcher([analyzer_a, analyzer_b])
        result = dispatcher.dispatch(["a.py"], _make_config())

        assert result.summary["ruff"] == 2
        assert result.summary["mypy"] == 1
        assert len(result.findings) == 3
