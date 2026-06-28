from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from coruscant.common.types import NormalizedDocument, SourceDocument


class RawDocumentRepository(ABC):
    @abstractmethod
    def save(self, document: SourceDocument) -> None:
        raise NotImplementedError


class NormalizedDocumentRepository(ABC):
    @abstractmethod
    def save(self, document: NormalizedDocument) -> None:
        raise NotImplementedError


class FileSystemRawDocumentRepository(RawDocumentRepository):
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, document: SourceDocument) -> None:
        path = self.root / "raw" / document.source_type / f"{document.source_id or document.uri_hash()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document.model_dump_json(indent=2))


class FileSystemNormalizedDocumentRepository(NormalizedDocumentRepository):
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, document: NormalizedDocument) -> None:
        path = self.root / "normalized" / document.document_type / f"{document.canonical_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document.model_dump_json(indent=2))
