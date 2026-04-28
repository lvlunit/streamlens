# Implementation Plan: Automated Code Review

## Overview

Replace the broken CLI-based code review workflow with a self-contained Python review engine. The engine uses a pluggable analyzer architecture to dispatch changed files to static analysis tools (ruff, mypy, tsc, bandit/trivy, hadolint), collect structured findings, and post them as inline PR review comments via the GitHub API. Implementation lives in `server/tools/review/` with tests in `server/tests/unit/` and `server/tests/property/`.

## Tasks

- [x] 1. Set up review engine package structure and core data models
  - [x] 1.1 Create the `server/tools/review/` package with `__init__.py`
    - Create directory `server/tools/review/`
    - Add `__init__.py` that exports core public types
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Implement core data models in `server/tools/review/models.py`
    - Define `Severity` enum with ERROR, WARNING, INFO values
    - Define `Finding` dataclass with file, line, severity, message, analyzer, rule_id, suggestion, end_line fields
    - Define `ReviewConfig` dataclass with repo_root, base_ref, head_ref, changed_files, severity_threshold, max_comments fields
    - Define `ReviewResult` dataclass with findings, summary, errors fields
    - Define `PRContext` dataclass with owner, repo, pr_number, base_sha, head_sha, token fields
    - Define `DiffMapping` dataclass with file, line, diff_position fields
    - Define `ReviewSummary` dataclass with total_findings, by_severity, by_analyzer, files_reviewed, files_with_findings, pass_status, duration_seconds, analyzer_errors fields
    - Add validation logic for Finding: file non-empty, line >= 1, message non-empty, end_line >= line when set
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 1.3 Write property test for Finding data validation (Property 12)
    - **Property 12: Finding data validity**
    - Use hypothesis to generate arbitrary Finding objects and verify all validation constraints hold: file non-empty, line >= 1, message non-empty, analyzer matches registered name, end_line >= line when set
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

  - [x] 1.4 Write unit tests for core data models
    - Test Severity enum values and ordering
    - Test Finding construction with valid and invalid data
    - Test ReviewConfig defaults (max_comments=50, severity_threshold=WARNING)
    - Test ReviewResult aggregation helpers
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 2. Implement diff computation and position mapping
  - [x] 2.1 Implement `git_diff_files()` in `server/tools/review/diff.py`
    - Run `git diff --name-only --diff-filter=d {base}...{head}` with `shell=False`
    - Exclude deleted files, return only files existing at head SHA
    - Validate file paths are safe relative paths (no traversal sequences)
    - _Requirements: 1.1, 1.2, 9.2, 9.3_

  - [x] 2.2 Implement `compute_diff_positions()` in `server/tools/review/diff.py`
    - Parse unified diff output line by line
    - Track current file, hunk position, and new-file line number
    - Generate DiffMapping for every added/modified line with correct 1-based diff position
    - Handle multi-hunk diffs and multiple files in a single diff
    - _Requirements: 4.1, 4.2_

  - [x] 2.3 Implement `filter_to_diff_lines()` in `server/tools/review/diff.py`
    - Build a set of (file, line) tuples from diff mappings for O(1) lookup
    - Return only findings whose (file, line) pair exists in the diff mapping set
    - Preserve relative order of findings
    - _Requirements: 4.3, 5.1, 7.5_

  - [x] 2.4 Write property test for diff mapping correctness (Property 5)
    - **Property 5: Diff mapping correctness**
    - Use hypothesis to generate valid unified diff strings and verify every DiffMapping references an added/modified line with correct file path, line number, and 1-based position
    - **Validates: Requirements 4.1, 4.2**

  - [x] 2.5 Write property test for finding-to-diff filtering (Property 6)
    - **Property 6: Finding-to-diff filtering**
    - Use hypothesis to generate lists of findings and diff mappings, verify filter_to_diff_lines returns only findings with matching (file, line) pairs and excludes all others
    - **Validates: Requirements 4.3, 5.1, 7.5**

  - [x] 2.6 Write property test for deleted file exclusion (Property 1)
    - **Property 1: Deleted file exclusion**
    - Use hypothesis to generate sets of file change records (added, modified, deleted), verify the changed file list excludes all deleted files
    - **Validates: Requirement 1.2**

  - [x] 2.7 Write unit tests for diff computation and position mapping
    - Test git_diff_files with known diff outputs (added, modified, deleted files)
    - Test compute_diff_positions with sample unified diffs (single hunk, multi-hunk, multi-file)
    - Test filter_to_diff_lines with findings on and off diff lines
    - Test file path validation rejects traversal sequences and absolute paths
    - _Requirements: 1.1, 1.2, 4.1, 4.2, 4.3, 9.3_

- [x] 3. Implement finding prioritization algorithm
  - [x] 3.1 Implement `prioritize_findings()` in `server/tools/review/prioritize.py`
    - Sort findings by severity (ERROR > WARNING > INFO), then by analyzer priority (security first)
    - Preserve relative order within each priority group (stable sort)
    - Truncate to exactly max_comments when count exceeds limit
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

  - [x] 3.2 Write property test for prioritization severity ordering (Property 7)
    - **Property 7: Prioritization severity and analyzer ordering**
    - Use hypothesis to generate lists of findings exceeding max_comments, verify ERROR before WARNING before INFO, and security findings before others within same severity
    - **Validates: Requirements 5.2, 5.3**

  - [x] 3.3 Write property test for prioritization count enforcement (Property 8)
    - **Property 8: Prioritization count enforcement**
    - Use hypothesis to generate findings lists exceeding max_comments, verify output length is exactly max_comments
    - **Validates: Requirement 5.4**

  - [x] 3.4 Write property test for prioritization stability (Property 9)
    - **Property 9: Prioritization stability**
    - Use hypothesis to generate findings, verify relative order is preserved within the same priority group
    - **Validates: Requirement 5.5**

  - [x] 3.5 Write unit tests for finding prioritization
    - Test with mixed severity findings and max_comments limit
    - Test security analyzer priority within same severity
    - Test exact count enforcement
    - Test with fewer findings than max_comments (no truncation)
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement BaseAnalyzer interface and AnalyzerDispatcher
  - [x] 5.1 Implement `BaseAnalyzer` abstract class in `server/tools/review/analyzers/base.py`
    - Create `server/tools/review/analyzers/` package with `__init__.py`
    - Define abstract properties: name, supported_extensions
    - Define abstract method: analyze(files, config) -> list[Finding]
    - Define concrete method: is_available() with subprocess check
    - Add file path validation helper that rejects traversal sequences and absolute paths
    - _Requirements: 3.1, 9.2, 9.3_

  - [x] 5.2 Implement `AnalyzerDispatcher` in `server/tools/review/dispatcher.py`
    - Accept list of BaseAnalyzer instances in constructor
    - Route each file to analyzers whose supported_extensions match the file extension
    - Never call an analyzer with an empty file list
    - Catch exceptions from individual analyzers, record in ReviewResult.errors
    - Aggregate findings into a single ReviewResult with accurate per-analyzer counts
    - Skip unavailable analyzers (is_available() returns False)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 7.1, 7.2_

  - [x] 5.3 Write property test for dispatch completeness (Property 2)
    - **Property 2: Dispatch completeness**
    - Use hypothesis to generate file lists and analyzer extension sets, verify every file is routed to every matching analyzer and no analyzer receives empty lists or mismatched extensions
    - **Validates: Requirements 2.1, 2.3**

  - [x] 5.4 Write property test for analyzer availability filtering (Property 3)
    - **Property 3: Analyzer availability filtering**
    - Use hypothesis to generate analyzer sets with mixed availability, verify only available analyzers are invoked
    - **Validates: Requirements 2.2, 7.2**

  - [x] 5.5 Write property test for finding aggregation accuracy (Property 4)
    - **Property 4: Finding aggregation accuracy**
    - Use hypothesis to generate per-analyzer finding lists, verify aggregated ReviewResult contains all findings and summary counts match
    - **Validates: Requirement 2.4**

  - [x] 5.6 Write property test for graceful degradation (Property 11)
    - **Property 11: Graceful degradation on analyzer failure**
    - Use hypothesis to generate analyzer sets where some raise exceptions, verify errors are captured and remaining analyzers complete
    - **Validates: Requirement 7.1**

  - [x] 5.7 Write unit tests for AnalyzerDispatcher
    - Test routing with multiple file types and analyzers
    - Test skipping unavailable analyzers
    - Test error handling when an analyzer raises an exception
    - Test empty file list handling
    - Test per-analyzer summary counts
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 7.1, 7.2_

- [x] 6. Implement concrete analyzers
  - [x] 6.1 Implement `RuffAnalyzer` in `server/tools/review/analyzers/ruff_analyzer.py`
    - Execute `ruff check --output-format=json` with `shell=False` on Python files
    - Parse JSON output into Finding objects with file, line, severity, message, rule_id
    - Map ruff severity levels to Severity enum
    - Validate file paths before passing to subprocess
    - _Requirements: 3.2, 9.2, 9.3, 9.5_

  - [x] 6.2 Implement `MypyAnalyzer` in `server/tools/review/analyzers/mypy_analyzer.py`
    - Execute `mypy` with structured output on Python files with `shell=False`
    - Parse output into Finding objects with type-checking diagnostics
    - Map mypy severity to Severity enum
    - _Requirements: 3.3, 9.2, 9.3, 9.5_

  - [x] 6.3 Implement `TypeScriptAnalyzer` in `server/tools/review/analyzers/typescript_analyzer.py`
    - Execute `tsc --noEmit` with `shell=False` on TypeScript files
    - Parse diagnostic output into Finding objects
    - Filter findings to only changed files
    - _Requirements: 3.4, 9.2, 9.3, 9.5_

  - [x] 6.4 Implement `SecurityAnalyzer` in `server/tools/review/analyzers/security_analyzer.py`
    - Execute `bandit` with JSON output on Python files with `shell=False`
    - Execute `trivy fs` with JSON output on the repository with `shell=False`
    - Combine findings from both tools
    - Map severity levels to Severity enum
    - _Requirements: 3.5, 9.2, 9.3, 9.4, 9.5_

  - [x] 6.5 Implement `DockerAnalyzer` in `server/tools/review/analyzers/docker_analyzer.py`
    - Match files named "Dockerfile" or with ".dockerfile" extension
    - Execute `hadolint` with JSON output with `shell=False`
    - Parse output into Finding objects
    - _Requirements: 3.6, 9.2, 9.3, 9.5_

  - [x] 6.6 Write property test for file path validation (Property 13)
    - **Property 13: File path validation for subprocess safety**
    - Use hypothesis to generate file paths including traversal sequences and absolute paths, verify all are rejected before subprocess execution
    - **Validates: Requirement 9.3**

  - [x] 6.7 Write unit tests for concrete analyzers
    - Test each analyzer with mocked subprocess calls and known tool output
    - Test RuffAnalyzer JSON parsing with sample ruff output
    - Test MypyAnalyzer output parsing with sample mypy output
    - Test TypeScriptAnalyzer tsc diagnostic parsing
    - Test SecurityAnalyzer bandit and trivy output parsing
    - Test DockerAnalyzer hadolint output parsing and Dockerfile matching
    - Test is_available() for each analyzer
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement GitHub PR Reporter
  - [x] 8.1 Implement `GitHubReporter` in `server/tools/review/reporter.py`
    - Use httpx to post a single atomic PR review via `POST /repos/{owner}/{repo}/pulls/{pr}/reviews`
    - Build review comments array from findings mapped to diff positions
    - Filter out findings whose lines are not in the diff
    - Include commit_sha in the review payload
    - _Requirements: 6.1, 6.4, 9.4_

  - [x] 8.2 Implement summary comment posting in `GitHubReporter`
    - Post a summary comment with total finding counts by severity and by analyzer
    - Include number of files reviewed and pass/fail status
    - Report pass if no ERROR-severity findings, fail otherwise
    - Note how many findings could not be posted inline (outside diff context)
    - Note which analyzers were skipped due to missing tools
    - _Requirements: 6.2, 6.3, 6.4, 7.2_

  - [x] 8.3 Implement retry logic with exponential backoff in `GitHubReporter`
    - Detect HTTP 403 rate limit responses
    - Retry up to 3 times with exponential backoff starting at 5 seconds
    - If all retries exhausted, fall back to posting a single summary comment
    - _Requirements: 7.3, 7.4_

  - [x] 8.4 Write property test for pass/fail status correctness (Property 10)
    - **Property 10: Pass/fail status correctness**
    - Use hypothesis to generate ReviewResult objects with varying severity distributions, verify pass_status is False iff any ERROR finding exists
    - **Validates: Requirement 6.3**

  - [x] 8.5 Write unit tests for GitHubReporter
    - Test review payload construction with mocked httpx
    - Test summary comment formatting with various finding distributions
    - Test pass/fail status logic
    - Test retry logic with mocked 403 responses
    - Test fallback to summary-only when retries exhausted
    - Test inline comment filtering for findings outside diff
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.3, 7.4_

- [x] 9. Implement the review engine orchestrator and entry point
  - [x] 9.1 Implement `run_review()` in `server/tools/review/engine.py`
    - Parse GitHub event payload from GITHUB_EVENT_PATH to extract PRContext
    - Compute changed files via git_diff_files()
    - Handle empty changed files case (post summary and exit)
    - Build ReviewConfig and initialize all analyzers
    - Filter to available analyzers, dispatch via AnalyzerDispatcher
    - Compute diff mappings, filter findings to diff lines
    - Apply prioritization when findings exceed max_comments
    - Post review and summary via GitHubReporter
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1, 5.2, 5.3, 5.4, 5.5, 9.1_

  - [x] 9.2 Create CLI entry point at `server/tools/review/run_review.py`
    - Read GITHUB_TOKEN and GITHUB_EVENT_PATH from environment
    - Parse event JSON and construct PRContext
    - Call run_review() and exit with code 1 if ERROR findings exist
    - _Requirements: 1.1, 9.1_

  - [x] 9.3 Write property test for review determinism (Property 14)
    - **Property 14: Review determinism**
    - Use hypothesis to generate PRContext and fixed analyzer outputs, verify two runs produce identical findings in the same order
    - **Validates: Requirement 10.1**

  - [x] 9.4 Write unit tests for the review engine orchestrator
    - Test full run_review flow with mocked git, analyzers, and GitHub API
    - Test empty changed files path
    - Test max_comments enforcement end-to-end
    - Test error aggregation from failed analyzers
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1, 9.1_

- [x] 10. Update GitHub Actions workflow and add dependencies
  - [x] 10.1 Update `.github/workflows/code-review.yml`
    - Replace the broken CLI-based workflow with the new review engine
    - Trigger on pull_request events to main/master branches
    - Set permissions to contents:read and pull-requests:write
    - Add checkout step with fetch-depth: 0 for full history
    - Add Python 3.12 setup step
    - Add Node.js setup step for TypeScript checking
    - Add tool installation step (pip install ruff mypy bandit, npm install -g typescript)
    - Add hadolint and trivy installation steps
    - Add review engine execution step with GITHUB_TOKEN
    - _Requirements: 9.1, 9.4_

  - [x] 10.2 Add review tool dependencies to project configuration
    - Create `server/tools/review/requirements.txt` with pinned versions for ruff, mypy, bandit, httpx, hypothesis
    - Add hypothesis to dev dependencies in `server/pyproject.toml`
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [x] 10.3 Write unit tests for GitHub Actions workflow configuration
    - Validate the workflow YAML has correct permissions (contents:read, pull-requests:write)
    - Validate the workflow triggers on pull_request events
    - Validate fetch-depth: 0 is set for full history
    - _Requirements: 9.1_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints at tasks 4, 7, and 11 ensure incremental validation
- Property tests use the hypothesis library as specified in the design
- All subprocess calls use `shell=False` per security requirements
- The review engine lives in `server/tools/review/` to keep it self-contained alongside the existing server code
- The existing broken workflow at `.github/workflows/code-review.yml` is replaced in task 10.1
