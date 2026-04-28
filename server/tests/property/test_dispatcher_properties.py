"""Properties 2, 3, 4, 11: Dispatcher properties."""
from hypothesis import given, strategies as st, assume
from unittest.mock import MagicMock
from tools.review.models import Finding, ReviewConfig, ReviewResult, Severity
from tools.review.dispatcher import AnalyzerDispatcher
from tools.review.analyzers.base import BaseAnalyzer
from pathlib import Path
import os

def make_mock_analyzer(name, extensions, available=True, findings=None, raises=None):
    analyzer = MagicMock(spec=BaseAnalyzer)
    analyzer.name = name
    analyzer.supported_extensions = extensions
    analyzer.is_available.return_value = available
    if raises:
        analyzer.analyze.side_effect = raises
    else:
        analyzer.analyze.return_value = findings or []
    return analyzer

# Property 2: Dispatch completeness
@given(
    file_extensions=st.lists(
        st.sampled_from([".py", ".ts", ".tsx", ".yml", ".dockerfile"]),
        min_size=1,
        max_size=10,
    ),
)
def test_dispatch_completeness(file_extensions):
    """Every file is routed to every matching analyzer.

    **Validates: Requirements 2.1, 2.3**
    """
    files = [f"file{i}{ext}" for i, ext in enumerate(file_extensions)]

    analyzer1 = make_mock_analyzer("a1", {".py"}, findings=[])
    analyzer2 = make_mock_analyzer("a2", {".ts", ".tsx"}, findings=[])

    config = ReviewConfig(repo_root=Path("."), base_ref="a", head_ref="b", changed_files=files)
    dispatcher = AnalyzerDispatcher(analyzers=[analyzer1, analyzer2])
    dispatcher.dispatch(files, config)

    # Check each analyzer was called with correct files
    if any(ext == ".py" for ext in file_extensions):
        analyzer1.analyze.assert_called()
        called_files = analyzer1.analyze.call_args[0][0]
        for f in called_files:
            _, ext = os.path.splitext(f)
            assert ext in analyzer1.supported_extensions

    if any(ext in (".ts", ".tsx") for ext in file_extensions):
        analyzer2.analyze.assert_called()
        called_files = analyzer2.analyze.call_args[0][0]
        for f in called_files:
            _, ext = os.path.splitext(f)
            assert ext in analyzer2.supported_extensions

# Property 3: Analyzer availability filtering
@given(
    available_flags=st.lists(st.booleans(), min_size=1, max_size=5),
)
def test_only_available_analyzers_invoked(available_flags):
    """Only available analyzers are invoked.

    **Validates: Requirements 2.2, 7.2**
    """
    analyzers = []
    for i, available in enumerate(available_flags):
        a = make_mock_analyzer(f"a{i}", {".py"}, available=available, findings=[])
        analyzers.append(a)

    config = ReviewConfig(repo_root=Path("."), base_ref="a", head_ref="b")
    dispatcher = AnalyzerDispatcher(analyzers=analyzers)
    dispatcher.dispatch(["test.py"], config)

    for i, a in enumerate(analyzers):
        if available_flags[i]:
            a.analyze.assert_called()
        else:
            a.analyze.assert_not_called()

# Property 4: Finding aggregation accuracy
@given(
    counts=st.lists(st.integers(min_value=0, max_value=10), min_size=1, max_size=5),
)
def test_finding_aggregation_accuracy(counts):
    """Aggregated result contains all findings with correct counts.

    **Validates: Requirement 2.4**
    """
    analyzers = []
    total_expected = 0
    for i, count in enumerate(counts):
        findings = [
            Finding(file="test.py", line=j+1, severity=Severity.WARNING, message=f"msg{j}", analyzer=f"a{i}")
            for j in range(count)
        ]
        a = make_mock_analyzer(f"a{i}", {".py"}, findings=findings)
        analyzers.append(a)
        total_expected += count

    config = ReviewConfig(repo_root=Path("."), base_ref="a", head_ref="b")
    dispatcher = AnalyzerDispatcher(analyzers=analyzers)
    result = dispatcher.dispatch(["test.py"], config)

    assert len(result.findings) == total_expected
    for i, count in enumerate(counts):
        if count > 0:
            assert result.summary.get(f"a{i}", 0) == count

# Property 11: Graceful degradation
@given(
    fail_indices=st.lists(st.integers(min_value=0, max_value=4), min_size=1, max_size=3, unique=True),
)
def test_graceful_degradation_on_failure(fail_indices):
    """Failed analyzers are captured; remaining analyzers complete.

    **Validates: Requirement 7.1**
    """
    assume(all(i < 5 for i in fail_indices))

    analyzers = []
    for i in range(5):
        if i in fail_indices:
            a = make_mock_analyzer(f"a{i}", {".py"}, raises=RuntimeError(f"fail {i}"))
        else:
            findings = [Finding(file="test.py", line=1, severity=Severity.WARNING, message="ok", analyzer=f"a{i}")]
            a = make_mock_analyzer(f"a{i}", {".py"}, findings=findings)
        analyzers.append(a)

    config = ReviewConfig(repo_root=Path("."), base_ref="a", head_ref="b")
    dispatcher = AnalyzerDispatcher(analyzers=analyzers)
    result = dispatcher.dispatch(["test.py"], config)

    # Errors captured
    assert len(result.errors) == len(fail_indices)
    # Successful analyzers produced findings
    expected_findings = 5 - len(fail_indices)
    assert len(result.findings) == expected_findings
