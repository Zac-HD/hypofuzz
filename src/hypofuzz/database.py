import json
from typing import Iterable, Union

from hypothesis import settings
from hypothesis.database import BackgroundWriteDatabase, ExampleDatabase

Report = dict[str, Union[int, float, str, list, dict[str, int]]]


def metadata_key(key: bytes) -> bytes:
    return key + b".hypofuzz.metadata"


class HypofuzzDatabase:
    def __init__(self, db: ExampleDatabase) -> None:
        self._db = db

    def save(self, key: bytes, value: bytes) -> None:
        self._db.save(key, value)

    def fetch(self, key: bytes) -> Iterable[bytes]:
        return self._db.fetch(key)

    def delete(self, key: bytes, value: bytes) -> None:
        self._db.delete(key, value)

    def save_metadata(self, key: bytes, report: Report) -> None:
        self._db.save(metadata_key(key), bytes(json.dumps(report), "ascii"))

    def delete_metadata(self, key: bytes, report: Report) -> None:
        self._db.delete(metadata_key(key), bytes(json.dumps(report), "ascii"))

    def fetch_metadata(self, key: bytes) -> Iterable[bytes]:
        return [json.loads(v) for v in self._db.fetch(metadata_key(key))]


db = HypofuzzDatabase(BackgroundWriteDatabase(settings.default.database))
