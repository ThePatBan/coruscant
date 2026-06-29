from __future__ import annotations

from pathlib import Path

from coruscant.common.types import NormalizedDocument
from coruscant.infrastructure.catalog import SqliteDocumentCatalog


def _catalog(tmp_path: Path) -> SqliteDocumentCatalog:
    return SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'catalog.db'}")


def _doc(canonical_id: str, document_type: str = "filing") -> NormalizedDocument:
    return NormalizedDocument(
        document_type=document_type,
        source_uri=f"reference://{canonical_id}",
        canonical_id=canonical_id,
        title=f"Title {canonical_id}",
        sections=[{"title": "S", "content": "body"}],
    )


def test_catalog_upsert_is_idempotent(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    catalog.upsert(_doc("x"), company_slug="apple", source_type="sec_edgar")
    catalog.upsert(_doc("x"), company_slug="apple", source_type="sec_edgar")
    assert catalog.count() == 1


def test_catalog_get_and_list_and_filters(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    catalog.upsert(_doc("x"), company_slug="apple", source_type="sec_edgar")
    catalog.upsert(_doc("y", "news_article"), company_slug="tesla", source_type="news")

    fetched = catalog.get("x")
    assert fetched is not None
    assert fetched.title == "Title x"
    assert fetched.sections[0]["content"] == "body"

    assert catalog.count() == 2
    assert catalog.companies() == ["apple", "tesla"]
    assert [d.canonical_id for d in catalog.list_documents(company_slug="tesla")] == ["y"]
    assert [d.canonical_id for d in catalog.list_documents(source_type="sec_edgar")] == ["x"]
    assert catalog.get("missing") is None


def test_catalog_persists_across_instances(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'catalog.db'}"
    SqliteDocumentCatalog(url).upsert(_doc("x"), company_slug="apple", source_type="sec_edgar")
    reopened = SqliteDocumentCatalog(url)
    assert reopened.count() == 1
    assert reopened.get("x") is not None
