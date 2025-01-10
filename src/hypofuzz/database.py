import json
from collections.abc import Iterable
from functools import cache
from typing import Union

from hypothesis import settings
from hypothesis.database import BackgroundWriteDatabase, ExampleDatabase

Report = dict[str, Union[int, float, str, list, dict[str, Union[int, str]]]]


def metadata_key(key: bytes) -> bytes:
    return key + b".hypofuzz.metadata"


class HypofuzzDatabase:
    def __init__(self, db: ExampleDatabase) -> None:
        self._db = db

    def save(self, key: bytes, value: bytes) -> None:
        self._db.save(key, value)

    def fetch(self, key: bytes) -> Iterable[bytes]:
        return self._db.fetch(key)  # type: ignore

    def delete(self, key: bytes, value: bytes) -> None:
        self._db.delete(key, value)

    def save_metadata(self, key: bytes, report: Report) -> None:
        self._db.save(metadata_key(key), bytes(json.dumps(report), "ascii"))

    def delete_metadata(self, key: bytes, report: Report) -> None:
        self._db.delete(metadata_key(key), bytes(json.dumps(report), "ascii"))

    def fetch_metadata(self, key: bytes) -> Iterable[Report]:
        return [json.loads(e) for e in self._db.fetch(metadata_key(key))]


# cache to make the db a singleton. We defer creation until first-usage to ensure
# that we use the test-time database setting, rather than init-time.
@cache
def get_db() -> HypofuzzDatabase:
    db = settings().database
    if isinstance(db, BackgroundWriteDatabase):
        return HypofuzzDatabase(db)
    return HypofuzzDatabase(BackgroundWriteDatabase(db))
