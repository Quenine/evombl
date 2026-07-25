from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


class SourceAdapter[T](ABC):
    """Interface only: network retrieval is intentionally not implemented."""

    @abstractmethod
    def parse(self, source_path: str) -> Iterable[T]:
        raise NotImplementedError
