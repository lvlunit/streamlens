"""Property 12: Finding data validity."""
from hypothesis import given, strategies as st
from tools.review.models import Finding, Severity
import pytest

# Strategy for valid findings
severities = st.sampled_from(list(Severity))
valid_analyzers = st.sampled_from(["ruff", "mypy", "typescript", "security", "docker"])

@given(
    file=st.text(min_size=1, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))),
    line=st.integers(min_value=1, max_value=10000),
    severity=severities,
    message=st.text(min_size=1, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
    analyzer=valid_analyzers,
    end_line_offset=st.integers(min_value=0, max_value=100) | st.none(),
)
def test_valid_finding_always_passes_validation(file, line, severity, message, analyzer, end_line_offset):
    """**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**"""
    end_line = line + end_line_offset if end_line_offset is not None else None
    f = Finding(file=file, line=line, severity=severity, message=message, analyzer=analyzer, end_line=end_line)
    assert f.file
    assert f.line >= 1
    assert f.message
    if f.end_line is not None:
        assert f.end_line >= f.line

# Test that invalid findings raise ValueError
@given(line=st.integers(max_value=0))
def test_invalid_line_raises(line):
    """**Validates: Requirements 8.2**"""
    with pytest.raises(ValueError):
        Finding(file="test.py", line=line, severity=Severity.ERROR, message="msg", analyzer="ruff")

@given(message=st.just(""))
def test_empty_message_raises(message):
    """**Validates: Requirements 8.3**"""
    with pytest.raises(ValueError):
        Finding(file="test.py", line=1, severity=Severity.ERROR, message=message, analyzer="ruff")

def test_empty_file_raises():
    """**Validates: Requirements 8.1**"""
    with pytest.raises(ValueError):
        Finding(file="", line=1, severity=Severity.ERROR, message="msg", analyzer="ruff")

@given(
    line=st.integers(min_value=1, max_value=100),
    end_line_offset=st.integers(min_value=-100, max_value=-1),
)
def test_end_line_less_than_line_raises(line, end_line_offset):
    """**Validates: Requirements 8.5**"""
    end_line = line + end_line_offset
    if end_line < line:
        with pytest.raises(ValueError):
            Finding(file="test.py", line=line, severity=Severity.ERROR, message="msg", analyzer="ruff", end_line=end_line)
