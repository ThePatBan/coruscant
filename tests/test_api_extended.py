from __future__ import annotations

from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.common.types import NormalizedDocument
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.projectors import ProjectingKnowledgeGraphStore
from coruscant.search.hybrid import HybridRetrievalEngine


def _document() -> NormalizedDocument:
    return NormalizedDocument(
        document_type="filing",
        source_uri="reference://sec_edgar/apple",
        canonical_id="cid1",
        title="Apple 10-K",
        sections=[
            {
                "title": "Item 1. Business",
                "content": "Apple designs devices and services",
                "anchor": "item-1-business",
                "evidence": [
                    {
                        "source_uri": "reference://sec_edgar/apple",
                        "excerpt": "Apple designs devices and services",
                        "section_title": "Item 1. Business",
                    }
                ],
            }
        ],
        entities=[{"kind": "Company", "key": "apple", "name": "Apple"}],
        metadata={"company_slug": "apple", "source_name": "sec_edgar"},
    )


def _client() -> TestClient:
    engine = HybridRetrievalEngine()
    graph = InMemoryKnowledgeGraphStore()
    document = _document()
    engine.add(document)
    ProjectingKnowledgeGraphStore(graph).project_document(document)
    return TestClient(create_app(engine, graph, require_auth=False))


def test_health_reports_counts() -> None:
    with _client() as client:
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["documents"] == 1
        assert body["graph_nodes"] >= 1


def test_companies_and_sources() -> None:
    with _client() as client:
        companies = client.get("/companies").json()
        assert {c["slug"] for c in companies} >= {"apple", "tesla"}
        sources = client.get("/sources").json()
        assert len(sources) == 13
        assert {s["source_type"] for s in sources} >= {
            "sec_edgar",
            "global_regulators",
            "sanctions",
            "court_filings",
        }


def test_documents_listing_and_detail() -> None:
    with _client() as client:
        listed = client.get("/documents", params={"company": "apple"}).json()
        assert [d["canonical_id"] for d in listed] == ["cid1"]
        detail = client.get("/documents/cid1").json()
        assert detail["sections"][0]["title"] == "Item 1. Business"
        assert client.get("/documents/missing").status_code == 404
        assert client.get("/documents", params={"company": "nobody"}).json() == []


def test_graph_endpoint() -> None:
    with _client() as client:
        found = client.get("/graph/company/apple").json()
        assert found["found"] is True
        assert any(n["relation"] == "filed" for n in found["neighbors"])
        missing = client.get("/graph/company/ghost").json()
        assert missing["found"] is False
        assert missing["neighbors"] == []


def test_retrieve_and_answer_keep_evidence() -> None:
    with _client() as client:
        retrieve = client.post("/retrieve", json={"query": "Apple devices", "top_k": 3}).json()
        assert "Apple 10-K" in retrieve["answer"]
        assert retrieve["results"][0]["evidence"][0]["section_title"] == "Item 1. Business"
        answer = client.get("/answer", params={"q": "Apple devices"}).json()
        assert "Apple 10-K" in answer["answer"]
