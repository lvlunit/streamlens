"""Property 14: Review determinism."""
from hypothesis import given, strategies as st
from unittest.mock import patch, MagicMock
from tools.review.models import Finding, PRContext, ReviewResult, Severity
from tools.review.engine import run_review

severities = st.sampled_from(list(Severity))
analyzers_names = st.sampled_from(["ruff", "mypy", "typescript", "security", "docker"])

@given(
    num_findings=st.integers(min_value=0, max_value=20),
    seed_line=st.integers(min_value=1, max_value=100),
)
def test_review_determinism(num_findings, seed_line):
    """Two runs with same inputs produce identical findings in same order.

    **Validates: Requirement 10.1**
    """
    pr_context = PRContext(
        owner="test", repo="repo", pr_number=1,
        base_sha="abc123", head_sha="def456", token="token"
    )

    fixed_findings = [
        Finding(file="test.py", line=seed_line + i, severity=Severity.WARNING, message=f"msg{i}", analyzer="ruff")
        for i in range(num_findings)
    ]

    mock_result = ReviewResult(findings=fixed_findings, summary={"ruff": num_findings})

    with patch("tools.review.engine.git_diff_files", return_value=["test.py"]), \
         patch("tools.review.engine.compute_diff_positions", return_value=[]), \
         patch("tools.review.engine.AnalyzerDispatcher") as mock_dispatcher_cls, \
         patch("tools.review.engine.GitHubReporter") as mock_reporter_cls, \
         patch("tools.review.engine.RuffAnalyzer") as mock_ruff, \
         patch("tools.review.engine.MypyAnalyzer") as mock_mypy, \
         patch("tools.review.engine.TypeScriptAnalyzer") as mock_ts, \
         patch("tools.review.engine.SecurityAnalyzer") as mock_sec, \
         patch("tools.review.engine.DockerAnalyzer") as mock_docker:

        for mock_a in [mock_ruff, mock_mypy, mock_ts, mock_sec, mock_docker]:
            mock_a.return_value.is_available.return_value = True

        mock_dispatcher_cls.return_value.dispatch.return_value = mock_result
        mock_reporter_cls.return_value = MagicMock()

        result1 = run_review(pr_context)
        result2 = run_review(pr_context)

        assert result1.findings == result2.findings
        assert result1.summary == result2.summary
