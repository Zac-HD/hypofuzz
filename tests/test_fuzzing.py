import pytest
from common import fuzz_with_no_error

# high-level tests that fuzzing something does not produce an error


@pytest.mark.parametrize(
    "code",
    [
        """
    @given(st.integers())
    def test_trivial(n):
        pass
    """,
        """
    @given(st.floats(allow_infinity=False, allow_nan=False) | st.integers())
    def test_targeting(v):
        target(v)
    """,
    ],
)
def test_fuzz_with_no_error(tmp_path, code):
    fuzz_with_no_error(tmp_path, code)
