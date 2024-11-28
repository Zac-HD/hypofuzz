import json
from typing import Iterable

from hypothesis import settings
from hypothesis.database import BackgroundWriteDatabase, ExampleDatabase


def metadata_key(key: bytes) -> bytes:
    return key + b".hypofuzz.metadata"


class MetadataDatabase(ExampleDatabase):
    def __init__(self, db: ExampleDatabase) -> None:
        self._db = db

    def save(self, key: bytes, value: bytes) -> None:
        self._db.save(key, value)

    def fetch(self, key: bytes) -> Iterable[bytes]:
        return self._db.fetch(key)

    def delete(self, key: bytes, value: bytes) -> None:
        self._db.delete(key, value)

    def save_metadata(self, key: bytes, value: bytes) -> None:
        self._db.save(metadata_key(key), value)

    def delete_metadata(self, key: bytes, value: bytes) -> None:
        self._db.delete(metadata_key(key), value)

    def fetch_metadata(self, key: bytes) -> Iterable[bytes]:
        return [json.loads(v) for v in db.fetch(metadata_key(key))]


db = MetadataDatabase(BackgroundWriteDatabase(settings.default.database))
