"""Analyzer dispatcher for the automated code review engine.

Routes changed files to the appropriate analyzers based on file
extension, aggregates findings, and handles individual analyzer failures
gracefully.
"""

from __future__ import annotations

import os
from collections import defaultdict

from .analyzers.base import BaseAnalyzer
from .models import ReviewConfig, ReviewResult


class AnalyzerDispatcher:
    """Routes files to appropriate analyzers and collects findings.

    Args:
        analyzers: List of :class:`BaseAnalyzer` instances to consider.
            Unavailable analyzers (where ``is_available()`` returns
            ``False``) are automatically skipped.
    """

    def __init__(self, analyzers: list[BaseAnalyzer]) -> None:
        self._analyzers = analyzers

    def dispatch(
        self,
        changed_files: list[str],
        config: ReviewConfig,
    ) -> ReviewResult:
        """Run all relevant analyzers against *changed_files*.

        Each file is routed to every available analyzer whose
        :attr:`~BaseAnalyzer.supported_extensions` includes the file's
        extension.  Analyzers are never called with an empty file list.

        If an analyzer raises an exception, the error is recorded in
        :attr:`ReviewResult.errors` and remaining analyzers continue.

        Returns:
            Aggregated :class:`ReviewResult` with all findings and
            per-analyzer summary counts.
        """
        result = ReviewResult()

        for analyzer in self._analyzers:
            # Skip unavailable analyzers
            if not analyzer.is_available():
                result.errors.append(
                    f"Analyzer '{analyzer.name}' skipped: tool not available"
                )
                continue

            # Collect files matching this analyzer's extensions
            matched_files = self._match_files(changed_files, analyzer)
            if not matched_files:
                continue

            try:
                findings = analyzer.analyze(matched_files, config)
                result.findings.extend(findings)
                result.summary[analyzer.name] = (
                    result.summary.get(analyzer.name, 0) + len(findings)
                )
            except Exception as exc:
                result.errors.append(
                    f"Analyzer '{analyzer.name}' failed: {exc}"
                )

        return result

    @staticmethod
    def _match_files(
        files: list[str],
        analyzer: BaseAnalyzer,
    ) -> list[str]:
        """Return files whose extension is in *analyzer.supported_extensions*."""
        extensions = analyzer.supported_extensions
        matched: list[str] = []
        for file_path in files:
            _, ext = os.path.splitext(file_path)
            if ext in extensions:
                matched.append(file_path)
        return matched
