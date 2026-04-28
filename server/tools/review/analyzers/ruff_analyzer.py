"""Ruff analyzer for Python linting.

Wraps the ``ruff check`` command to produce structured findings from
Python source files.
"""

from __future__ import annotations

import json
import subprocess

from ..models import Finding, ReviewConfig, Severity
from .base import BaseAnalyzer


class RuffAnalyzer(BaseAnalyzer):
    """Python linting and formatting via ruff."""

    @property
    def name(self) -> str:
        return "ruff"

    @property
    def supported_extensions(self) -> set[str]:
        return {".py", ".pyi"}

    def analyze(self, files: list[str], config: ReviewConfig) -> list[Finding]:
        """Run ``ruff check --output-format=json`` on the given Python files.

        Args:
            files: Python file paths relative to the repository root.
            config: Review configuration with repo root and settings.

        Returns:
            List of :class:`Finding` objects for issues detected by ruff.
        """
        self.validate_file_paths(files)

        try:
            result = subprocess.run(
                ["ruff", "check", "--output-format=json", *files],
                capture_output=True,
                text=True,
                shell=False,
                cwd=str(config.repo_root),
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        output = result.stdout.strip()
        if not output:
            return []

        try:
            diagnostics = json.loads(output)
        except json.JSONDecodeError:
            return []

        findings: list[Finding] = []
        for diag in diagnostics:
            code = diag.get("code", "") or ""
            severity = self._map_severity(code)
            message = diag.get("message", "")
            filename = diag.get("filename", "")
            location = diag.get("location", {})
            line = location.get("row", 1)
            end_location = diag.get("end_location", {})
            end_line = end_location.get("row")

            if not filename or not message:
                continue

            finding = Finding(
                file=filename,
                line=line,
                severity=severity,
                message=message,
                analyzer=self.name,
                rule_id=code if code else None,
                end_line=end_line if end_line and end_line >= line else None,
            )
            findings.append(finding)

        return findings

    @staticmethod
    def _map_severity(code: str) -> Severity:
        """Map a ruff rule code to a :class:`Severity` level.

        Rules starting with ``E`` are errors, ``W`` are warnings,
        and everything else is informational.
        """
        if code.startswith("E"):
            return Severity.ERROR
        if code.startswith("W"):
            return Severity.WARNING
        return Severity.INFO
