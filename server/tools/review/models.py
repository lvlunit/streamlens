"""Core data models for the automated code review engine."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(Enum):
    """Severity levels for code review findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single code review finding tied to a specific file and line.

    Attributes:
        file: Relative path from repo root.
        line: 1-based line number.
        severity: ERROR, WARNING, or INFO.
        message: Human-readable description of the issue.
        analyzer: Name of the analyzer that produced this finding.
        rule_id: Tool-specific rule ID (e.g., "E501", "TS2345").
        suggestion: Optional fix suggestion.
        end_line: End line for multi-line findings.
    """

    file: str
    line: int
    severity: Severity
    message: str
    analyzer: str
    rule_id: str | None = None
    suggestion: str | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        if not self.file:
            raise ValueError("Finding.file must be non-empty")
        if self.line < 1:
            raise ValueError(f"Finding.line must be >= 1, got {self.line}")
        if not self.message:
            raise ValueError("Finding.message must be non-empty")
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError(
                f"Finding.end_line ({self.end_line}) must be >= line ({self.line})"
            )


@dataclass
class ReviewConfig:
    """Configuration for a review run."""

    repo_root: Path
    base_ref: str
    head_ref: str
    changed_files: list[str] = field(default_factory=list)
    severity_threshold: Severity = Severity.WARNING
    max_comments: int = 50


@dataclass
class ReviewResult:
    """Aggregated result of all analyzers."""

    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class PRContext:
    """Metadata extracted from the GitHub event payload."""

    owner: str
    repo: str
    pr_number: int
    base_sha: str
    head_sha: str
    token: str


@dataclass
class DiffMapping:
    """Maps a file and line number to a position within the unified diff."""

    file: str
    line: int
    diff_position: int


@dataclass
class ReviewSummary:
    """Summary statistics for a completed review run."""

    total_findings: int
    by_severity: dict[Severity, int]
    by_analyzer: dict[str, int]
    files_reviewed: int
    files_with_findings: int
    pass_status: bool
    duration_seconds: float
    analyzer_errors: list[str]
