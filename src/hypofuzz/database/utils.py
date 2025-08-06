from base64 import b64decode, b64encode
from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar, Union, overload

from hypothesis.internal.conjecture.choice import ChoiceT

if TYPE_CHECKING:
    from typing import TypeAlias


T = TypeVar("T", covariant=True)

ChoicesT: "TypeAlias" = tuple[ChoiceT, ...]


class HashableIterable(Protocol[T]):
    def __hash__(self) -> int: ...
    def __iter__(self) -> Iterator[T]: ...


@overload
def convert_db_key(key: str, *, to: Literal["bytes"]) -> bytes: ...


@overload
def convert_db_key(key: bytes, *, to: Literal["str"]) -> str: ...


def convert_db_key(
    key: Union[str, bytes], *, to: Literal["str", "bytes"]
) -> Union[str, bytes]:
    if to == "str":
        assert isinstance(key, bytes)
        return b64encode(key).decode("ascii")
    elif to == "bytes":
        assert isinstance(key, str)
        return b64decode(key.encode("ascii"))
    else:
        raise ValueError(f"Invalid conversion {to=}")
