"""Property 13: File path validation for subprocess safety."""
from hypothesis import given, strategies as st, assume
from tools.review.analyzers.base import BaseAnalyzer
import pytest

# Generate paths with traversal sequences
@given(
    prefix=st.text(min_size=0, max_size=5, alphabet="abcdef"),
    suffix=st.text(min_size=1, max_size=10, alphabet="abcdef.py"),
)
def test_traversal_paths_rejected(prefix, suffix):
    """Paths containing '..' are always rejected.

    **Validates: Requirement 9.3**
    """
    # Ensure '..' is a proper path component by using '/' separators
    if prefix:
        path = f"{prefix}/../{suffix}"
    else:
        path = f"../{suffix}"
    with pytest.raises(ValueError):
        BaseAnalyzer.validate_file_paths([path])

@given(path=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnop./"))
def test_absolute_paths_rejected(path):
    """Absolute paths are always rejected.

    **Validates: Requirement 9.3**
    """
    abs_path = "/" + path  # Ensure it starts with /
    with pytest.raises(ValueError):
        BaseAnalyzer.validate_file_paths([abs_path])

@given(
    parts=st.lists(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"), min_size=1, max_size=4),
)
def test_valid_relative_paths_accepted(parts):
    """Valid relative paths without traversal are accepted.

    **Validates: Requirement 9.3**
    """
    path = "/".join(parts) + ".py"
    assume(".." not in path)
    result = BaseAnalyzer.validate_file_paths([path])
    assert result == [path]
