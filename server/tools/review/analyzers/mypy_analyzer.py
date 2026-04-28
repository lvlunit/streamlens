"""Mypy analyzer for Python type checking.

Wraps the ``mypy`` command to produce structured findings from
Python source files.
"""

from __future__ import annotations

import re
import subprocess

from ..models import Finding, ReviewConfig, Severity
from .base import BaseAnalyzer

# Pattern: file:line:col: severity: message
_MYPY_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<severity>\w+):\s*(?P<message>.+)$"
)


class MypyAnalyzer(BaseAnalyzer):
    """Python type checking via mypy."""

    @property
    def name(self) -> str:
        return "mypy"

    @property
    def supported_extensions(self) -> set[str]:
        return {".py", ".pyi"}

    def analyze(self, files: list[str], config: ReviewConfig) -> list[Finding]:
        """Run mypy on the given Python files and parse diagnostics.

        Args:
            files: Python file paths relative to the repository root.
            config: Review configuration with repo root and settings.

        Returns:
            List of :class:`Finding` objects for type-checking issues.
        """
        self.validate_file_paths(files)

        try:
            result = subprocess.run(
                [
                    "mypy",
                    "--no-error-summary",
                    "--show-column-numbers",
                    "--no-color",
                    *files,
                ],
                capture_output=True,
                text=True,
                shell=False,
                cwd=str(config.repo_root),
                timeout=300,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        output = result.stdout.strip()
        if not output:
            return []

        findings: list[Finding] = []
        for line in output.splitlines():
            match = _MYPY_LINE_RE.match(line.strip())
            if not match:
                continue

            filename = match.group("file")
            line_no = int(match.group("line"))
            severity_str = match.group("severity").lower()
            message = match.group("message").strip()

            if not filename or not message:
                continue

            severity = self._map_severity(severity_str)

            findings.append(
                Finding(
                    file=filename,
                    line=line_no,
                    severity=severity,
                    message=message,
                    analyzer=self.name,
                )
            )

        return findings

    @staticmethod
    def _map_severity(severity_str: str) -> Severity:
        """Map a mypy severity string to a :class:`Severity` level."""
        if severity_str == "error":
            return Severity.ERROR
        if severity_str == "warning":
            return Severity.WARNING
        return Severity.INFO
