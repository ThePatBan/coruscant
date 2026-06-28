from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)


def test_filesystem_repositories_write_json(tmp_path: Path) -> None:
    raw_repo = FileSystemRawDocumentRepository(tmp_path)
    normalized_repo = FileSystemNormalizedDocumentRepository(tmp_path)
    raw_document = SourceDocument(
        source_type="sec_edgar",
        source_uri="https://example.com/filing",
        fetched_at=datetime.now(tz=timezone.utc),
        raw_content="content",
    )
    normalized_document = NormalizedDocument(
        document_type="filing",
        source_uri="https://example.com/filing",
        canonical_id="abc123",
    )

    raw_repo.save(raw_document)
    normalized_repo.save(normalized_document)

    assert list((tmp_path / "raw" / "sec_edgar").glob("*.json"))
    assert list((tmp_path / "normalized" / "filing").glob("abc123.json"))
