"""Property 10: Pass/fail status correctness."""
from hypothesis import given, strategies as st
from tools.review.models import Finding, ReviewResult, Severity
from tools.review.reporter import GitHubReporter

severities = st.sampled_from(list(Severity))
analyzers = st.sampled_from(["ruff", "mypy", "typescript", "security", "docker"])

@given(
    findings=st.lists(
        st.builds(
            Finding,
            file=st.just("test.py"),
            line=st.integers(min_value=1, max_value=100),
            severity=severities,
            message=st.just("test"),
            analyzer=analyzers,
        ),
        min_size=0,
        max_size=30,
    ),
)
def test_pass_fail_status_correctness(findings):
    """pass_status is False iff any ERROR finding exists.

    **Validates: Requirement 6.3**
    """
    result = ReviewResult(findings=findings)

    has_error = any(f.severity == Severity.ERROR for f in findings)

    # The summary format includes pass/fail - verify the logic
    summary = GitHubReporter._format_summary(result, files_reviewed=1, skipped_analyzers=[], unmapped_count=0)

    if has_error:
        assert "❌ **FAIL**" in summary
    else:
        assert "✅ **PASS**" in summary
