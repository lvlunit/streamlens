"""Abstract base class for all code review analyzers.

Every concrete analyzer must subclass :class:`BaseAnalyzer` and implement
the ``name``, ``supported_extensions``, and ``analyze`` members.
"""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

from ..models import Finding, ReviewConfig


class BaseAnalyzer(ABC):
    """Interface for all code review analyzers.

    Concrete subclasses wrap a specific static analysis tool (e.g. ruff,
    mypy, tsc) and translate its output into :class:`Finding` objects.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable analyzer name (e.g. ``'ruff'``)."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """File extensions this analyzer handles (e.g. ``{'.py', '.pyi'}``)."""
        ...

    @abstractmethod
    def analyze(self, files: list[str], config: ReviewConfig) -> list[Finding]:
        """Run analysis on *files* and return findings.

        Args:
            files: File paths relative to the repository root.  All paths
                are guaranteed to have extensions in
                :attr:`supported_extensions`.
            config: Review configuration with repo root and settings.

        Returns:
            List of :class:`Finding` objects for issues detected.
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether the underlying tool is installed and runnable.

        The default implementation tries to execute the tool named
        :attr:`name` with ``--version``.  Subclasses may override this
        if the tool uses a different availability check.
        """
        try:
            subprocess.run(
                [self.name, "--version"],
                capture_output=True,
                check=True,
                shell=False,
                timeout=10,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def validate_file_paths(files: list[str]) -> list[str]:
        """Validate and return only safe relative file paths.

        Rejects paths that contain traversal sequences (``..``) or are
        absolute paths.  This **must** be called before passing file
        paths to any subprocess.

        Args:
            files: Candidate file paths.

        Returns:
            The same list if all paths are valid.

        Raises:
            ValueError: If any path is unsafe.
        """
        for path in files:
            if not path:
                raise ValueError("Empty file path")
            if os.path.isabs(path) or path.startswith("/"):
                raise ValueError(f"Absolute path not allowed: {path}")
            parts = PurePosixPath(path).parts
            if ".." in parts:
                raise ValueError(f"Path traversal not allowed: {path}")
        return files
