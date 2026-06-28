from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from coruscant.common.types import SourceDocument
from coruscant.connectors.base import FetchRequest
from coruscant.connectors.sec_edgar import (
    EdgarHttpConnector,
    ReferenceEdgarConnector,
    _parse_index_exhibits,
    _parse_index_metadata,
    _parse_primary_document_url,
    normalize_edgar_filing,
)


def test_reference_edgar_connector_produces_item_sections() -> None:
    connector = ReferenceEdgarConnector()
    document = connector.fetch(
        FetchRequest(
            company_slug="apple",
            source_name="10-K",
            source_uri="reference://sec_edgar/apple",
            company_name="Apple",
            period="2025-01-31",
        )
    )
    normalized = normalize_edgar_filing(document)

    assert document.metadata["provenance"] == "reference-sample"
    assert normalized.document_type == "filing"
    assert len(normalized.sections) == 3
    assert normalized.sections[0]["title"].lower().startswith("item 1.")
    assert normalized.entities[0]["key"] == "apple"
    assert str(normalized.published_at) == "2025-01-31"


def test_normalize_edgar_filing() -> None:
    document = SourceDocument(
        source_type="sec_edgar",
        source_uri="https://example.com/filing",
        fetched_at=datetime.now(tz=timezone.utc),
        raw_content=Path("tests/fixtures/sec_edgar/10-k-primary.txt").read_text(),
        metadata={"filing_date": "2025-01-31", "company_slug": "apple", "form_type": "10-K"},
    )
    normalized = normalize_edgar_filing(document)
    assert normalized.document_type == "filing"
    assert len(normalized.sections) == 3
    assert normalized.sections[0]["title"].lower().startswith("item 1.")
    assert "Apple designs devices and services." in normalized.sections[0]["content"]
    assert normalized.sections[0]["evidence"][0]["source_uri"] == document.source_uri
    assert str(normalized.published_at) == "2025-01-31"
    assert normalized.entities[0]["key"] == "apple"


def test_parse_index_json_like_payload() -> None:
    payload = {
        "filing": {
            "accessionNumber": "0000320193-25-000079",
            "filingDate": "2025-01-31",
            "periodOfReport": "2024-12-31",
            "companyName": "Apple Inc.",
        },
        "directory": {
            "item": [
                {"type": "10-K", "name": "primary document", "href": "/Archives/foo/a10-k.htm"},
                {"name": "exhibit21.htm", "href": "/Archives/foo/ex21.htm"},
            ]
        },
    }

    metadata = _parse_index_metadata(payload)
    primary_url = _parse_primary_document_url(payload, "https://www.sec.gov/Archives/foo/index.json")
    exhibits = _parse_index_exhibits(payload)

    assert metadata["accession_number"] == "0000320193-25-000079"
    assert metadata["company_name"] == "Apple Inc."
    assert primary_url == "https://www.sec.gov/Archives/foo/a10-k.htm"
    assert exhibits and exhibits[0]["url"] == "/Archives/foo/ex21.htm"


def test_edgar_http_connector_uses_index_json(monkeypatch) -> None:
    fixture_dir = Path("tests/fixtures/sec_edgar")
    filing_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/a10-k20250927.htm"
    index_url = urljoin(filing_url, "index.json")
    index_payload = (fixture_dir / "index.json").read_text()
    primary_payload = (fixture_dir / "10-k-primary.txt").read_text()

    class _Response:
        def __init__(self, text: str, content_type: str = "application/json") -> None:
            self._text = text
            self.headers = {"content-type": content_type}

        def read(self) -> bytes:
            return self._text.encode("utf-8")

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        url = request.full_url if hasattr(request, "full_url") else request
        if url == index_url:
            return _Response(index_payload)
        if url == filing_url:
            return _Response(primary_payload, "text/html")
        if url.endswith("a10-k20250927.htm"):
            return _Response(primary_payload, "text/html")
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("coruscant.connectors.sec_edgar.urlopen", fake_urlopen)

    connector = EdgarHttpConnector(user_agent="Coruscant/0.1.0 test")
    document = connector.fetch(
        FetchRequest(
            company_slug="apple",
            source_name="10-K",
            source_uri=filing_url,
        )
    )

    assert document.metadata["accession_number"] == "0000320193-25-000079"
    assert document.metadata["primary_document_url"].endswith("a10-k20250927.htm")
    assert document.metadata["indexed_exhibits"]
    assert "Apple designs devices and services." in document.raw_content


def test_form_specific_section_templates() -> None:
    forms = {
        "10-K": (Path("tests/fixtures/sec_edgar/10-k-primary.txt"), 3),
        "10-Q": (Path("tests/fixtures/sec_edgar/10-q-primary.txt"), 2),
        "8-K": (Path("tests/fixtures/sec_edgar/8-k-primary.txt"), 2),
        "DEF 14A": (Path("tests/fixtures/sec_edgar/def14a-primary.txt"), 2),
    }

    for form_type, (path, expected_count) in forms.items():
        document = SourceDocument(
            source_type="sec_edgar",
            source_uri=f"https://example.com/{form_type.lower().replace(' ', '-')}",
            fetched_at=datetime.now(tz=timezone.utc),
            raw_content=path.read_text(),
            metadata={"form_type": form_type, "company_slug": "apple", "filing_date": "2025-01-31"},
        )
        normalized = normalize_edgar_filing(document)
        assert len(normalized.sections) == expected_count
        assert normalized.sections[0]["evidence"][0]["source_uri"] == document.source_uri
