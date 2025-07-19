import pytest
from common import fuzz_with_no_error


@pytest.mark.parametrize(
    "code",
    [
        """
    class Test(TestCase):
        @given(st.integers())
        def test_trivial(self, n):
            assert isinstance(self, Test)
            assert isinstance(n, int)
    """,
        """
    class Test(TestCase):
        def setUp(self):
            self.a = 1

        @given(st.integers())
        def test_requires_setup(self, n):
            assert isinstance(self, Test)
            assert isinstance(n, int)
            assert self.a == 1
    """,
        """
    class Test(TestCase):
        @classmethod
        def setUpClass(cls):
            cls.a = 1

        @given(st.integers())
        def test_requires_setup_class(self, n):
            assert isinstance(self, Test)
            assert isinstance(n, int)
            assert self.a == 1
    """,
    ],
)
def test_fuzz_with_no_error(tmp_path, code):
    fuzz_with_no_error(tmp_path, code)
