"""Diff computation, position mapping, and finding filtering.

Provides utilities to compute changed files from git diffs, map file lines
to diff positions for the GitHub review API, and filter findings to only
those visible in the PR diff.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import PurePosixPath

from .models import DiffMapping, Finding


def _validate_file_path(path: str) -> bool:
    """Check that a file path is a safe relative path.

    Rejects absolute paths and paths containing traversal sequences.
    """
    if not path:
        return False
    if os.path.isabs(path) or path.startswith("/"):
        return False
    # Reject any component that is ".."
    parts = PurePosixPath(path).parts
    if ".." in parts:
        return False
    return True


def git_diff_files(base_sha: str, head_sha: str) -> list[str]:
    """Return list of changed files between base and head commits.

    Runs ``git diff --name-only --diff-filter=d`` to get files that were
    added or modified (excluding deleted files).  Each returned path is
    validated to be a safe relative path.

    Args:
        base_sha: Base commit SHA or ref.
        head_sha: Head commit SHA or ref.

    Returns:
        Sorted list of relative file paths that exist at *head_sha*.

    Raises:
        subprocess.CalledProcessError: If the git command fails.
        ValueError: If any returned path fails validation.
    """
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=d",
            f"{base_sha}...{head_sha}",
        ],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )

    files: list[str] = []
    for line in result.stdout.strip().splitlines():
        path = line.strip()
        if not path:
            continue
        if not _validate_file_path(path):
            raise ValueError(f"Unsafe file path in diff output: {path}")
        files.append(path)

    return files


def _parse_file_path(diff_git_line: str) -> str | None:
    """Extract the file path from a ``diff --git a/... b/...`` line."""
    match = re.match(r"^diff --git a/.+ b/(.+)$", diff_git_line)
    if match:
        return match.group(1)
    return None


def _parse_hunk_header(hunk_line: str) -> int:
    """Extract the new-file starting line number from a hunk header.

    A hunk header looks like ``@@ -old_start,old_count +new_start,new_count @@``.
    Returns the *new_start* value.
    """
    match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", hunk_line)
    if match:
        return int(match.group(1))
    return 1


def compute_diff_positions(base_sha: str, head_sha: str) -> list[DiffMapping]:
    """Parse unified diff output to map file+line to diff positions.

    Runs ``git diff --unified=3`` and walks the output line by line,
    tracking the current file, hunk position, and new-file line number.
    A :class:`DiffMapping` is generated for every added/modified line
    (lines starting with ``+`` that are not the ``+++`` header).

    Args:
        base_sha: Base commit SHA or ref.
        head_sha: Head commit SHA or ref.

    Returns:
        List of :class:`DiffMapping` entries with 1-based diff positions.
    """
    result = subprocess.run(
        ["git", "diff", f"{base_sha}...{head_sha}", "--unified=3"],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )

    diff_output = result.stdout
    mappings: list[DiffMapping] = []
    current_file: str | None = None
    position = 0
    current_new_line = 0

    for raw_line in diff_output.splitlines():
        if raw_line.startswith("diff --git"):
            current_file = _parse_file_path(raw_line)
            position = 0
        elif raw_line.startswith("@@"):
            current_new_line = _parse_hunk_header(raw_line)
            position += 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            position += 1
            if current_file is not None:
                mappings.append(
                    DiffMapping(
                        file=current_file,
                        line=current_new_line,
                        diff_position=position,
                    )
                )
            current_new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            position += 1
        else:
            # Context line or file header (---, +++)
            if not raw_line.startswith("---") and not raw_line.startswith("+++"):
                position += 1
                current_new_line += 1

    return mappings


def filter_to_diff_lines(
    findings: list[Finding],
    diff_mappings: list[DiffMapping],
) -> list[Finding]:
    """Keep only findings on lines that appear in the diff.

    Builds a set of ``(file, line)`` tuples from *diff_mappings* for O(1)
    lookup, then returns findings whose ``(file, line)`` pair exists in
    that set.  The relative order of findings is preserved.

    Args:
        findings: All findings from analyzers.
        diff_mappings: Diff position mappings from :func:`compute_diff_positions`.

    Returns:
        Filtered list of findings visible in the diff.
    """
    diff_lines: set[tuple[str, int]] = {
        (m.file, m.line) for m in diff_mappings
    }
    return [f for f in findings if (f.file, f.line) in diff_lines]
