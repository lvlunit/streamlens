"""Docker analyzer for Dockerfile linting.

Wraps the ``hadolint`` command to produce structured findings from
Dockerfiles.
"""

from __future__ import annotations

import json
import os
import subprocess

from ..models import Finding, ReviewConfig, Severity
from .base import BaseAnalyzer


class DockerAnalyzer(BaseAnalyzer):
    """Dockerfile linting via hadolint."""

    @property
    def name(self) -> str:
        return "docker"

    @property
    def supported_extensions(self) -> set[str]:
        return {".dockerfile"}

    def is_available(self) -> bool:
        """Check whether ``hadolint`` is installed and runnable."""
        try:
            subprocess.run(
                ["hadolint", "--version"],
                capture_output=True,
                check=True,
                shell=False,
                timeout=10,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def analyze(self, files: list[str], config: ReviewConfig) -> list[Finding]:
        """Run ``hadolint --format json`` on Dockerfiles.

        In addition to files with a ``.dockerfile`` extension, this
        analyzer also matches files whose basename is ``Dockerfile``
        (case-sensitive), regardless of extension.

        Args:
            files: File paths relative to the repository root.
            config: Review configuration with repo root and settings.

        Returns:
            List of :class:`Finding` objects for Dockerfile issues.
        """
        self.validate_file_paths(files)

        dockerfiles = self._match_dockerfiles(files)
        if not dockerfiles:
            return []

        try:
            result = subprocess.run(
                ["hadolint", "--format", "json", *dockerfiles],
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
            filename = diag.get("file", "")
            line = diag.get("line", 1)
            level = (diag.get("level") or "").lower()
            message = diag.get("message", "")
            code = diag.get("code", "")

            if not filename or not message:
                continue

            severity = self._map_severity(level)

            findings.append(
                Finding(
                    file=filename,
                    line=line,
                    severity=severity,
                    message=message,
                    analyzer=self.name,
                    rule_id=code if code else None,
                )
            )

        return findings

    @staticmethod
    def _match_dockerfiles(files: list[str]) -> list[str]:
        """Return files named ``Dockerfile`` or with a ``.dockerfile`` extension."""
        matched: list[str] = []
        for file_path in files:
            basename = os.path.basename(file_path)
            _, ext = os.path.splitext(file_path)
            if basename == "Dockerfile" or ext == ".dockerfile":
                matched.append(file_path)
        return matched

    @staticmethod
    def _map_severity(level: str) -> Severity:
        """Map a hadolint severity level to :class:`Severity`."""
        if level == "error":
            return Severity.ERROR
        if level == "warning":
            return Severity.WARNING
        return Severity.INFO
