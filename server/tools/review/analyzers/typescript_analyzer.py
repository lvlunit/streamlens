"""TypeScript analyzer for type checking.

Wraps the ``tsc`` compiler to produce structured findings from
TypeScript source files.
"""

from __future__ import annotations

import re
import subprocess

from ..models import Finding, ReviewConfig, Severity
from .base import BaseAnalyzer

# Pattern: file(line,col): error TSxxxx: message
_TSC_LINE_RE = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s*error\s+(?P<code>TS\d+):\s*(?P<message>.+)$"
)


class TypeScriptAnalyzer(BaseAnalyzer):
    """TypeScript type checking via tsc."""

    @property
    def name(self) -> str:
        return "typescript"

    @property
    def supported_extensions(self) -> set[str]:
        return {".ts", ".tsx"}

    def is_available(self) -> bool:
        """Check whether ``tsc`` is installed and runnable."""
        try:
            subprocess.run(
                ["tsc", "--version"],
                capture_output=True,
                check=True,
                shell=False,
                timeout=10,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def analyze(self, files: list[str], config: ReviewConfig) -> list[Finding]:
        """Run ``tsc --noEmit --pretty false`` and parse diagnostics.

        Only findings referencing files in *files* are returned, since
        ``tsc`` may report errors across the entire project.

        Args:
            files: TypeScript file paths relative to the repository root.
            config: Review configuration with repo root and settings.

        Returns:
            List of :class:`Finding` objects for type-checking issues.
        """
        self.validate_file_paths(files)

        try:
            result = subprocess.run(
                ["tsc", "--noEmit", "--pretty", "false"],
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

        # Normalise the set of changed files for fast lookup
        changed_set = set(files)

        findings: list[Finding] = []
        for line in output.splitlines():
            match = _TSC_LINE_RE.match(line.strip())
            if not match:
                continue

            filename = match.group("file").strip()
            line_no = int(match.group("line"))
            code = match.group("code")
            message = match.group("message").strip()

            if not filename or not message:
                continue

            # Filter to only changed files
            if filename not in changed_set:
                continue

            findings.append(
                Finding(
                    file=filename,
                    line=line_no,
                    severity=Severity.ERROR,
                    message=message,
                    analyzer=self.name,
                    rule_id=code,
                )
            )

        return findings
