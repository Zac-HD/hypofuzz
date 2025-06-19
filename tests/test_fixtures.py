from common import collect_names, fuzz, setup_test_code, wait_for, wait_for_test_key
from hypothesis.database import DirectoryBasedExampleDatabase

from hypofuzz.database import HypofuzzDatabase, test_keys_key


def assert_no_failures(db, key):
    assert not list(db.fetch_failures(key, shrunk=True))
    assert not list(db.fetch_failures(key, shrunk=False))


def assert_fixtures(tmp_path, code, *, test_name):
    assert collect_names(code) == {test_name}
    test_dir, db_dir = setup_test_code(tmp_path, code)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    with fuzz(test_dir):
        key = wait_for_test_key(db, timeout=2)
        wait_for(lambda: len(db.fetch_reports(key)) > 0, interval=0.1)
        assert_no_failures(db, key)


def test_basic_fixture(tmp_path):
    code = """
    @pytest.fixture
    def a():
        return "a"

    @given(st.just(None))
    def test_a(a, _none):
        assert _none is None
        assert a == "a"
    """
    assert_fixtures(tmp_path, code, test_name="test_a")


def test_fixture_order(tmp_path):
    code = """
    @pytest.fixture
    def order(): return []

    @pytest.fixture
    def a(order): order.append("a")
    @pytest.fixture
    def b(a, order): order.append("b")
    @pytest.fixture
    def c(b, order): order.append("c")
    @pytest.fixture
    def d(c, b, order): order.append("d")
    @pytest.fixture
    def e(d, b, order): order.append("e")
    @pytest.fixture
    def f(e, order): order.append("f")
    @pytest.fixture
    def g(f, c, order): order.append("g")

    @given(st.just(None))
    def test_order(g, order, _none):
        assert _none is None
        assert order == ["a", "b", "c", "d", "e", "f", "g"], order
    """
    assert_fixtures(tmp_path, code, test_name="test_order")


def test_fixture_teardown(tmp_path):
    code = """
    a_active = False
    b_active = False

    @pytest.fixture
    def a():
        global a_active
        assert not a_active

        a_active = True
        yield "a"
        a_active = False

    @pytest.fixture
    def b():
        global b_active
        assert not b_active

        b_active = True
        yield "b"
        b_active = False

    @given(st.just(None))
    def test_a(a, _none):
        assert _none is None
        assert a == "a"

    @given(st.just(None))
    def test_b(b, _none):
        assert _none is None
        assert b == "b"
    """
    assert collect_names(code) == {"test_a", "test_b"}
    test_dir, db_dir = setup_test_code(tmp_path, code)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    with fuzz(test_dir):
        # wait for it to run both tests
        wait_for(lambda: len(list(db.fetch(test_keys_key))) == 2, interval=0.1)
        keys = list(db.fetch(test_keys_key))
        assert len(keys) == 2

        for key in keys:
            wait_for(lambda: len(db.fetch_reports(key)) > 0, interval=0.1)
        for key in keys:
            assert_no_failures(db, key)


def test_scoped_fixtures(tmp_path):
    code = """
    @pytest.fixture(scope="session")
    def order(): return []

    @pytest.fixture
    def func(order): order.append("function")

    @pytest.fixture(scope="class")
    def cls(order): order.append("class")

    @pytest.fixture(scope="module")
    def mod(order): order.append("module")

    @pytest.fixture(scope="package")
    def pack(order): order.append("package")

    @pytest.fixture(scope="session")
    def sess(order): order.append("session")

    @given(st.just(None))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_order(func, cls, mod, pack, sess, order, _none):
        assert _none is None
        assert order == ["session", "package", "module", "class", "function"]

    """
    assert_fixtures(tmp_path, code, test_name="test_order")


def test_uses_autouse_fixture(tmp_path):
    code = """
    autouse_value = None
    @pytest.fixture(autouse=True)
    def autouse():
        global autouse_value
        autouse_value = "global_autouse_value"

    @given(st.just(None))
    def test_a(_none):
        assert _none is None
        assert autouse_value == "global_autouse_value"
    """
    assert_fixtures(tmp_path, code, test_name="test_a")
