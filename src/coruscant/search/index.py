from __future__ import annotations

from abc import ABC, abstractmethod

from coruscant.common.types import NormalizedDocument


class SearchIndex(ABC):
    @abstractmethod
    def index(self, document: NormalizedDocument) -> None:
        raise NotImplementedError
