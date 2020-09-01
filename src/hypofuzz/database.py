"""Hypothesis database tools for fuzzing use-cases."""

from typing import Callable, Iterable

from hypothesis.database import (
    DirectoryBasedExampleDatabase,
    ExampleDatabase,
    InMemoryExampleDatabase,
)
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule
from hypothesis.strategies import binary

__all__ = [
    "DirectoryBasedExampleDatabase",
    "ExampleDatabase",
    "InMemoryExampleDatabase",
    "MultiplexedDatabase",
    "ReadOnlyDatabase",
]


class ReadOnlyDatabase(ExampleDatabase):
    """A wrapper to make the given database read-only.

    .. note::

        This wrapper intentionally disables Hypothesis' automatic discarding of
        stale examples.  It is designed to allow local machines to access a
        shared database (e.g. from CI servers), without propogating changes
        back from a local or in-development branch.
    """

    def __init__(self, db: ExampleDatabase) -> None:
        assert isinstance(db, ExampleDatabase)
        self._wrapped = db

    def fetch(self, key: bytes) -> Iterable[bytes]:
        yield from self._wrapped.fetch(key)

    def save(self, key: bytes, value: bytes) -> None:
        pass

    def delete(self, key: bytes, value: bytes) -> None:
        pass

    def move(self, src: bytes, dest: bytes, value: bytes) -> None:
        pass


class MultiplexedDatabase(ExampleDatabase):
    """A wrapper around multiple databases.

    Combines well with a :class:`ReadOnlyDatabase`, as follows:

    .. code-block:: python

        local = DirectoryBasedExampleDatabase("/tmp/hypothesis/examples/")
        shared = CustomNetworkDatabase()

        settings.register_profile("ci", database=shared)
        settings.register_profile(
            "dev", database=MultiplexedDatabase(local, ReadOnlyDatabase(shared))
        )
        settings.load_profile("ci" if os.environ.get("CI") else "dev")

    So your CI system (and fuzzing runs) can populate a central shared database;
    while local runs on development machines can reproduce any failures from CI
    but will only cache their own failures locally and cannot remove examples
    from the shared database.

    .. note::

        Hypothesis ExampleDatabases do not distinguish between branches,
        pull requests, etc.  If you want to separate these namespaces you
        will need additional logic extending the example above.

    """

    def __init__(self, *dbs: ExampleDatabase) -> None:
        assert all(isinstance(db, ExampleDatabase) for db in dbs)
        self._wrapped = dbs

    def fetch(self, key: bytes) -> Iterable[bytes]:
        seen = set()
        for db in self._wrapped:
            for value in db.fetch(key):
                if value not in seen:
                    yield value
                    seen.add(value)

    def save(self, key: bytes, value: bytes) -> None:
        for db in self._wrapped:
            db.save(key, value)

    def delete(self, key: bytes, value: bytes) -> None:
        for db in self._wrapped:
            db.delete(key, value)

    def move(self, src: bytes, dest: bytes, value: bytes) -> None:
        for db in self._wrapped:
            db.move(src, dest, value)


class DatabaseComparison(RuleBasedStateMachine):
    """Get a stateful test which checks an ExampleDatabase implementation.

    This is most useful if you've defined your own custom ExampleDatabase class,
    which might e.g. use a networked key-value store to share the database
    between CI servers and your team's local runs.

    Arguments to a ``DatabaseComparison`` must be callables which return an
    ExampleDatabase itself.  This can be the class itself if no arguments are
    required, a trivial lambda, or a more complicated function to include any
    setup or configuration logic.  For example:

    .. code-block:: python

        TestMyDB = DatabaseComparison(MyCustomDB, lambda: AnotherDB(args)).TestCase

    """

    def __init__(self, *db_factories: Callable[[], RuleBasedStateMachine]) -> None:
        super().__init__()
        self.databases = (InMemoryExampleDatabase(),) + tuple(f() for f in db_factories)
        assert db_factories
        assert all(isinstance(db, ExampleDatabase) for db in self.databases)

    keys = Bundle("keys")
    values = Bundle("values")

    @rule(target=keys, k=binary())  # type: ignore
    def k(self, k: bytes) -> bytes:
        return k

    @rule(target=values, v=binary())  # type: ignore
    def v(self, v: bytes) -> bytes:
        return v

    @rule(k=keys, v=values)  # type: ignore
    def save(self, k: bytes, v: bytes) -> None:
        for db in self.databases:
            db.save(k, v)

    @rule(k=keys, v=values)  # type: ignore
    def delete(self, k: bytes, v: bytes) -> None:
        for db in self.databases:
            db.delete(k, v)

    @rule(k1=keys, k2=keys, v=values)  # type: ignore
    def move(self, k1: bytes, k2: bytes, v: bytes) -> None:
        for db in self.databases:
            db.move(k1, k2, v)

    @rule(k=keys)  # type: ignore
    def values_agree(self, k: bytes) -> None:
        good = set(self.databases[0].fetch(k))
        for db in self.databases[1:]:
            assert set(db.fetch(k)) == good, (self.databases[0], db)
