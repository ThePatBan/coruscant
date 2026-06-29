from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from coruscant.common.types import SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.ingestion.reference import SecEdgarReferencePipeline
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.reference import ReferenceGraphProjector
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)


class _StubConnector(SourceConnector):
    def fetch(self, request: FetchRequest) -> SourceDocument:
        return SourceDocument(
            source_type="sec_edgar",
            source_uri=request.source_uri,
            fetched_at=datetime.now(tz=timezone.utc),
            raw_content="<html><body>Item 1. Business Exhibit 21</body></html>",
            source_name=request.source_name,
            metadata={"company_slug": request.company_slug, "title": "10-K"},
        )


def test_reference_pipeline_persists_raw_and_normalized(tmp_path: Path) -> None:
    graph_store = InMemoryKnowledgeGraphStore()
    pipeline = SecEdgarReferencePipeline(
        _StubConnector(),
        FetchRequest(
            company_slug="apple",
            source_name="10-K",
            source_uri="https://example.com/filing",
        ),
        FileSystemRawDocumentRepository(tmp_path),
        FileSystemNormalizedDocumentRepository(tmp_path),
        projector=ReferenceGraphProjector(),
        graph_store=graph_store,
    )

    result = pipeline.run()

    raw_files = list((tmp_path / "raw" / "sec_edgar").glob("*.json"))
    normalized_files = list((tmp_path / "normalized" / "filing").glob("*.json"))

    assert result.normalized_document.title == "10-K"
    assert raw_files
    assert normalized_files
    assert graph_store.nodes
