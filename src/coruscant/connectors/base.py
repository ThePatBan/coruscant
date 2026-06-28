from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from coruscant.common.types import SourceDocument


@dataclass(frozen=True)
class FetchRequest:
    company_slug: str
    source_name: str
    source_uri: str
    company_name: str | None = None
    industry: str | None = None
    period: str | None = None


class SourceConnector(ABC):
    @abstractmethod
    def fetch(self, request: FetchRequest) -> SourceDocument:
        raise NotImplementedError
