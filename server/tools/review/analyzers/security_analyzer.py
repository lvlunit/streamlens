"""Security analyzer combining bandit and trivy.

Runs ``bandit`` on Python files and ``trivy fs`` on the repository root
to detect security vulnerabilities.
"""

from __future__ import annotations

import json
import subprocess

from ..models import Finding, ReviewConfig, Severity
from .base import BaseAnalyzer


class SecurityAnalyzer(BaseAnalyzer):
    """Security scanning via bandit (Python) and trivy (general)."""

    @property
    def name(self) -> str:
        return "security"

    @property
    def supported_extensions(self) -> set[str]:
        return {".py", ".ts", ".tsx", ".js", ".yml", ".yaml", ".dockerfile"}

    def is_available(self) -> bool:
        """Check whether both ``bandit`` and ``trivy`` are installed."""
        bandit_ok = self._check_tool("bandit")
        trivy_ok = self._check_tool("trivy")
        return bandit_ok or trivy_ok

    def analyze(self, files: list[str], config: ReviewConfig) -> list[Finding]:
        """Run bandit on Python files and trivy on the repo root.

        Args:
            files: File paths relative to the repository root.
            config: Review configuration with repo root and settings.

        Returns:
            Combined list of :class:`Finding` objects from both tools.
        """
        self.validate_file_paths(files)

        findings: list[Finding] = []

        # Run bandit on Python files
        python_files = [f for f in files if f.endswith((".py", ".pyi"))]
        if python_files and self._check_tool("bandit"):
            findings.extend(self._run_bandit(python_files, config))

        # Run trivy on the repo root
        if self._check_tool("trivy"):
            findings.extend(self._run_trivy(config))

        return findings

    def _run_bandit(
        self, files: list[str], config: ReviewConfig
    ) -> list[Finding]:
        """Execute ``bandit -f json`` on the given Python files."""
        try:
            result = subprocess.run(
                ["bandit", "-f", "json", *files],
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
            data = json.loads(output)
        except json.JSONDecodeError:
            return []

        findings: list[Finding] = []
        for issue in data.get("results", []):
            severity_str = (issue.get("issue_severity") or "").upper()
            severity = self._map_bandit_severity(severity_str)
            filename = issue.get("filename", "")
            line = issue.get("line_number", 1)
            message = issue.get("issue_text", "")
            test_id = issue.get("test_id", "")

            if not filename or not message:
                continue

            findings.append(
                Finding(
                    file=filename,
                    line=line,
                    severity=severity,
                    message=message,
                    analyzer=self.name,
                    rule_id=test_id if test_id else None,
                )
            )

        return findings

    def _run_trivy(self, config: ReviewConfig) -> list[Finding]:
        """Execute ``trivy fs --format json --scanners vuln`` on the repo."""
        try:
            result = subprocess.run(
                [
                    "trivy",
                    "fs",
                    "--format",
                    "json",
                    "--scanners",
                    "vuln",
                    str(config.repo_root),
                ],
                capture_output=True,
                text=True,
                shell=False,
                timeout=300,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        output = result.stdout.strip()
        if not output:
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return []

        findings: list[Finding] = []
        for target_result in data.get("Results", []):
            target_file = target_result.get("Target", "")
            for vuln in target_result.get("Vulnerabilities", []):
                severity_str = (vuln.get("Severity") or "").upper()
                severity = self._map_trivy_severity(severity_str)
                vuln_id = vuln.get("VulnerabilityID", "")
                title = vuln.get("Title", "")
                pkg = vuln.get("PkgName", "")
                message = f"{vuln_id}: {title}" if title else vuln_id
                if pkg:
                    message = f"{pkg} - {message}"

                if not message:
                    continue

                findings.append(
                    Finding(
                        file=target_file if target_file else ".",
                        line=1,
                        severity=severity,
                        message=message,
                        analyzer=self.name,
                        rule_id=vuln_id if vuln_id else None,
                    )
                )

        return findings

    @staticmethod
    def _check_tool(tool_name: str) -> bool:
        """Check whether a CLI tool is available."""
        try:
            subprocess.run(
                [tool_name, "--version"],
                capture_output=True,
                check=True,
                shell=False,
                timeout=10,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _map_bandit_severity(severity_str: str) -> Severity:
        """Map bandit severity to :class:`Severity`."""
        if severity_str == "HIGH":
            return Severity.ERROR
        if severity_str == "MEDIUM":
            return Severity.WARNING
        return Severity.INFO

    @staticmethod
    def _map_trivy_severity(severity_str: str) -> Severity:
        """Map trivy severity to :class:`Severity`."""
        if severity_str in ("CRITICAL", "HIGH"):
            return Severity.ERROR
        if severity_str == "MEDIUM":
            return Severity.WARNING
        return Severity.INFO
