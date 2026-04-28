"""Properties 7, 8, 9: Prioritization properties."""
from hypothesis import given, strategies as st, assume
from tools.review.models import Finding, Severity
from tools.review.prioritize import prioritize_findings

severities = st.sampled_from(list(Severity))
analyzers = st.sampled_from(["ruff", "mypy", "typescript", "security", "docker"])

finding_strategy = st.builds(
    Finding,
    file=st.just("test.py"),
    line=st.integers(min_value=1, max_value=1000),
    severity=severities,
    message=st.just("test message"),
    analyzer=analyzers,
)

# Property 7: Severity and analyzer ordering
@given(
    findings=st.lists(finding_strategy, min_size=2, max_size=50),
    max_count=st.integers(min_value=1, max_value=10),
)
def test_prioritization_severity_ordering(findings, max_count):
    """**Validates: Requirements 5.2, 5.3**"""
    assume(len(findings) > max_count)
    result = prioritize_findings(findings, max_count)

    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    for i in range(len(result) - 1):
        assert severity_order[result[i].severity] <= severity_order[result[i+1].severity]

# Property 8: Count enforcement
@given(
    findings=st.lists(finding_strategy, min_size=2, max_size=100),
    max_count=st.integers(min_value=1, max_value=50),
)
def test_prioritization_count_enforcement(findings, max_count):
    """**Validates: Requirement 5.4**"""
    assume(len(findings) > max_count)
    result = prioritize_findings(findings, max_count)
    assert len(result) == max_count

# Property 9: Stability
@given(findings=st.lists(finding_strategy, min_size=2, max_size=50))
def test_prioritization_stability(findings):
    """Relative order preserved within same priority group.

    **Validates: Requirement 5.5**
    """
    max_count = len(findings)  # No truncation
    result = prioritize_findings(findings, max_count)

    # Group by priority key
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    analyzer_priority = {"security": 0, "ruff": 1, "mypy": 1, "typescript": 1, "docker": 2}

    def priority_key(f):
        return (severity_order.get(f.severity, 3), analyzer_priority.get(f.analyzer, 3))

    # Within each group, original order should be preserved
    from itertools import groupby
    groups = {}
    for f in findings:
        key = priority_key(f)
        groups.setdefault(key, []).append(f)

    result_groups = {}
    for f in result:
        key = priority_key(f)
        result_groups.setdefault(key, []).append(f)

    for key, original_group in groups.items():
        if key in result_groups:
            result_group = result_groups[key]
            # Check that result_group is a subsequence of original_group
            orig_indices = []
            for rf in result_group:
                for i, of in enumerate(original_group):
                    if rf is of and i not in orig_indices:
                        orig_indices.append(i)
                        break
            assert orig_indices == sorted(orig_indices)
