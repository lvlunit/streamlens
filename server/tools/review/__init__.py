"""Automated code review engine package.

Provides a pluggable analyzer architecture for running static analysis
tools on changed files and reporting findings as PR review comments.
"""

from .models import (
    DiffMapping,
    Finding,
    PRContext,
    ReviewConfig,
    ReviewResult,
    ReviewSummary,
    Severity,
)

__all__ = [
    "DiffMapping",
    "Finding",
    "PRContext",
    "ReviewConfig",
    "ReviewResult",
    "ReviewSummary",
    "Severity",
]
