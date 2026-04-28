# Requirements Document

## Introduction

This document defines the requirements for the Automated Code Review feature for StreamLens. The system is a self-contained Python review engine that runs as a GitHub Actions workflow on every pull request. It computes the diff of changed files, dispatches them to pluggable static analysis tools (ruff, mypy, ESLint/tsc, bandit/trivy, hadolint), collects structured findings, and posts them as inline PR review comments via the GitHub API. The goal is to replace a broken CLI-based approach with fast, accurate, file-specific feedback that references concrete lines and rules.

## Glossary

- **Review_Engine**: The top-level orchestrator that coordinates diff computation, analyzer dispatch, finding collection, and reporting for a single pull request review run.
- **Analyzer**: A component that wraps a specific static analysis tool and implements the BaseAnalyzer interface to produce structured findings from source files.
- **Analyzer_Dispatcher**: The component that routes changed files to the appropriate analyzers based on file extension and aggregates their results.
- **GitHub_Reporter**: The component that posts findings as inline PR review comments and a summary comment via the GitHub API.
- **Finding**: A structured data object representing a single code issue tied to a specific file, line number, severity, message, and originating analyzer.
- **DiffMapping**: A data object that maps a file and line number to a position within the unified diff output, used by the GitHub review API for inline comment placement.
- **ReviewConfig**: Configuration for a review run, including repository root, base/head refs, changed file list, severity threshold, and maximum comment count.
- **ReviewResult**: The aggregated output of all analyzers, containing a list of findings, per-analyzer counts, and any analyzer error messages.
- **PRContext**: Metadata extracted from the GitHub event payload, including repository owner, repo name, PR number, base/head SHAs, and the GitHub token.
- **Severity**: An enumeration of finding importance levels: ERROR, WARNING, and INFO.

## Requirements

### Requirement 1: Diff Computation and File Classification

**User Story:** As a developer, I want the review engine to identify only the files changed in my pull request, so that the review is fast and focused on my actual changes.

#### Acceptance Criteria

1. WHEN a pull request event is received, THE Review_Engine SHALL compute the list of changed files by comparing the base SHA and head SHA of the pull request.
2. WHEN the list of changed files is computed, THE Review_Engine SHALL exclude deleted files and include only files that exist at the head SHA.
3. WHEN changed files are identified, THE Review_Engine SHALL classify each file by its extension to determine which analyzers apply.
4. WHEN the pull request diff contains no changed files, THE Review_Engine SHALL post a summary comment stating no files were changed and exit successfully without running any analyzers.

### Requirement 2: Analyzer Dispatching

**User Story:** As a developer, I want changed files to be routed to the correct analysis tools based on file type, so that each file is checked by the appropriate linter or scanner.

#### Acceptance Criteria

1. WHEN changed files are dispatched, THE Analyzer_Dispatcher SHALL route each file to every available Analyzer whose supported_extensions set includes that file's extension.
2. WHEN an Analyzer is not available because its underlying tool is not installed, THE Analyzer_Dispatcher SHALL skip that Analyzer and continue dispatching to remaining analyzers.
3. WHEN dispatching files to an Analyzer, THE Analyzer_Dispatcher SHALL pass only files with matching extensions and never call an Analyzer with an empty file list.
4. THE Analyzer_Dispatcher SHALL aggregate findings from all analyzers into a single ReviewResult with accurate per-analyzer counts.

### Requirement 3: Analyzer Interface and Concrete Analyzers

**User Story:** As a maintainer, I want a uniform analyzer interface so that new analysis tools can be added without modifying the dispatch or reporting logic.

#### Acceptance Criteria

1. THE Analyzer SHALL implement the BaseAnalyzer interface, providing a name, a set of supported_extensions, an analyze method, and an is_available check.
2. WHEN the RuffAnalyzer is invoked with Python files, THE RuffAnalyzer SHALL execute ruff with JSON output and return a list of Finding objects with file, line, severity, message, and rule_id populated.
3. WHEN the MypyAnalyzer is invoked with Python files, THE MypyAnalyzer SHALL execute mypy and return a list of Finding objects with type-checking diagnostics.
4. WHEN the TypeScriptAnalyzer is invoked with TypeScript files, THE TypeScriptAnalyzer SHALL execute tsc with noEmit and return a list of Finding objects with type-checking diagnostics.
5. WHEN the SecurityAnalyzer is invoked, THE SecurityAnalyzer SHALL execute bandit on Python files and trivy on the repository and return a list of Finding objects for security vulnerabilities.
6. WHEN the DockerAnalyzer is invoked, THE DockerAnalyzer SHALL execute hadolint on Dockerfiles (files named "Dockerfile" or with a ".dockerfile" extension) and return a list of Finding objects.

### Requirement 4: Diff Position Mapping

**User Story:** As a developer, I want review comments to appear inline on the exact lines I changed, so that I can see feedback in context without searching for it.

#### Acceptance Criteria

1. WHEN the unified diff is parsed, THE Review_Engine SHALL produce a DiffMapping for every added or modified line, containing the file path, the line number in the new file, and the 1-based position within the diff hunk.
2. WHEN a DiffMapping is produced, THE Review_Engine SHALL ensure the mapped line is an added or modified line in the diff and the diff_position is the correct 1-based offset within the diff output.
3. WHEN a finding references a line that does not appear in the diff, THE Review_Engine SHALL exclude that finding from inline comments but still count it in the summary.

### Requirement 5: Finding Filtering and Prioritization

**User Story:** As a developer, I want only relevant findings posted on my PR and the most critical ones prioritized, so that I am not overwhelmed by noise.

#### Acceptance Criteria

1. WHEN findings are collected, THE Review_Engine SHALL filter them to include only findings on lines that are visible in the PR diff.
2. WHEN the number of visible findings exceeds the configured max_comments limit, THE Review_Engine SHALL select findings by priority: all ERROR-severity findings first, then WARNING, then INFO.
3. WHEN findings are prioritized within the same severity level, THE Review_Engine SHALL rank security analyzer findings above other analyzer findings.
4. WHEN findings are truncated to the max_comments limit, THE Review_Engine SHALL return exactly max_comments findings.
5. THE Review_Engine SHALL preserve the relative order of findings within each priority group after prioritization.

### Requirement 6: GitHub PR Reporting

**User Story:** As a developer, I want findings posted as a single atomic PR review with inline comments and a summary, so that I get a clean, consolidated review experience.

#### Acceptance Criteria

1. WHEN findings are ready to be reported, THE GitHub_Reporter SHALL post all inline comments as a single atomic PR review using the GitHub Pull Request Review API.
2. WHEN a review is posted, THE GitHub_Reporter SHALL include a summary comment with total finding counts broken down by severity and by analyzer, the number of files reviewed, and a pass/fail status.
3. WHEN the pass/fail status is determined, THE GitHub_Reporter SHALL report a failing status if any ERROR-severity findings exist and a passing status otherwise.
4. WHEN findings could not be posted inline because their lines are outside the diff context, THE GitHub_Reporter SHALL note in the summary comment how many findings could not be posted inline.

### Requirement 7: Error Handling and Graceful Degradation

**User Story:** As a maintainer, I want the review pipeline to be resilient to individual tool failures, so that a single broken analyzer does not block the entire review.

#### Acceptance Criteria

1. IF an Analyzer raises an exception during analyze(), THEN THE Analyzer_Dispatcher SHALL catch the exception, record the error message in ReviewResult.errors, and continue running remaining analyzers.
2. IF an Analyzer's underlying tool is not installed, THEN THE Analyzer_Dispatcher SHALL skip that Analyzer and note the skip in the summary comment.
3. IF the GitHub API returns an HTTP 403 rate limit response, THEN THE GitHub_Reporter SHALL retry with exponential backoff up to 3 retries starting at 5 seconds.
4. IF all GitHub API retries are exhausted, THEN THE GitHub_Reporter SHALL post a single summary comment instead of inline comments, noting that rate limits prevented inline feedback.
5. IF a finding's file and line cannot be mapped to a diff position, THEN THE Review_Engine SHALL exclude that finding from inline comments and include it only in the summary count.

### Requirement 8: Finding Data Validation

**User Story:** As a maintainer, I want all findings to be well-formed and valid, so that the reporting layer can rely on consistent data.

#### Acceptance Criteria

1. THE Finding SHALL have a non-empty file field that is a valid relative path existing in the repository.
2. THE Finding SHALL have a line field with a value greater than or equal to 1.
3. THE Finding SHALL have a non-empty message field.
4. THE Finding SHALL have an analyzer field that matches a registered analyzer name.
5. WHEN a Finding has an end_line value set, THE Finding SHALL have an end_line value greater than or equal to its line value.

### Requirement 9: Security and Isolation

**User Story:** As a security-conscious maintainer, I want the review engine to operate with minimal permissions and no risk of leaking secrets, so that the CI pipeline remains secure.

#### Acceptance Criteria

1. THE Review_Engine SHALL require only contents:read and pull-requests:write GitHub token permissions.
2. THE Review_Engine SHALL execute all analyzer tool subprocesses with shell=False to prevent command injection.
3. THE Review_Engine SHALL validate file paths before passing them to analyzer subprocesses.
4. THE Review_Engine SHALL make no outbound network calls except to the GitHub API.
5. THE Analyzer SHALL not include file contents or secret values in finding messages, limiting output to file paths, line numbers, and tool-generated diagnostic messages.

### Requirement 10: Determinism and Idempotency

**User Story:** As a developer, I want the review to produce the same results when run multiple times on the same commit, so that I can trust the feedback is consistent.

#### Acceptance Criteria

1. WHEN the Review_Engine is run twice on the same PR and commit SHA with the same analyzer versions, THE Review_Engine SHALL produce the same set of findings.
