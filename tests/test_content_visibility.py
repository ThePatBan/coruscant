"""Phase 7, Scope A — the public/private content-visibility boundary.

Mixed public/private fixtures prove that an anonymous visitor on the public read
surface can retrieve ONLY explicitly public, evidence-safe records: never a private
document, its detail/summary, its retrieval evidence, a diff against it, a restricted
graph edge, or restricted ownership data. Authenticated callers keep broader
visibility (analyst = legitimate-interest; admin = everything), so the guard is a
forward-safety gate, not a behaviour change for today's all-public corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.intelligence.models import Claim, DocumentSummary
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.search.hybrid import HybridRetrievalEngine


def _doc(canonical_id: str, title: str, term: str, *, tier: str | None = None) -> NormalizedDocument:
    metadata: dict[str, object] = {"company_slug": "acme", "source_name": "sec_edgar"}
    if tier is not None:
        metadata["access_tier"] = tier
    uri = f"reference://sec_edgar/{canonical_id}"
    return NormalizedDocument(
        document_type="filing",
        source_uri=uri,
        canonical_id=canonical_id,
        title=title,
        sections=[
            {
                "title": "Body",
                "content": f"Acme {term} disclosure",
                "evidence": [
                    {"source_uri": uri, "excerpt": f"Acme {term} disclosure", "section_title": "Body"}
                ],
            }
        ],
        entities=[{"kind": "Company", "key": "acme", "name": "Acme"}],
        metadata=metadata,
    )


# canonical_id -> (title, distinctive query term, tier)
PUBLIC_DOC = _doc("pub1", "Acme Public 10-K", "market")
LEGIT_DOC = _doc("legit1", "Acme Restricted Filing", "diligence", tier="legitimate-interest")
PRIVATE_DOC = _doc("priv1", "Acme Confidential Memo", "sealed", tier="restricted-authority")


def _summary(doc: NormalizedDocument) -> DocumentSummary:
    claim = Claim(text=f"Overview of {doc.title}", source_uri=doc.source_uri, canonical_id=doc.canonical_id)
    return DocumentSummary(
        canonical_id=doc.canonical_id,
        company_slug="acme",
        document_type="filing",
        source_type="sec_edgar",
        title=doc.title,
        source_uri=doc.source_uri,
        overview=claim,
    )


def _graph() -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key="acme", properties={"name": "Acme"}))
    store.upsert_node(GraphNode(kind="Country", key="us", properties={"name": "United States"}))
    store.upsert_node(GraphNode(kind="Person", key="jane", properties={"name": "Jane Roe"}))
    # A public reference edge — visible to everyone.
    store.upsert_edge(
        GraphEdge(
            source_kind="Company",
            source_key="acme",
            relation="operates_in",
            target_kind="Country",
            target_key="us",
            properties={"source": "reference"},
        )
    )
    # A restricted control edge — must be withheld from anonymous callers.
    store.upsert_edge(
        GraphEdge(
            source_kind="Company",
            source_key="acme",
            relation="controlled_by",
            target_kind="Person",
            target_key="jane",
            properties={"access_tier": "restricted-authority", "source": "psc"},
        )
    )
    return store


def _engine() -> HybridRetrievalEngine:
    engine = HybridRetrievalEngine()
    for doc in (PUBLIC_DOC, LEGIT_DOC, PRIVATE_DOC):
        engine.add(doc)
    return engine


def _intel(tmp_path: Path) -> SqliteIntelligenceStore:
    store = SqliteIntelligenceStore(f"sqlite:///{tmp_path / 'intel.db'}")
    for doc in (PUBLIC_DOC, LEGIT_DOC, PRIVATE_DOC):
        store.save_summary(_summary(doc))
    return store


def _anon_client(tmp_path: Path) -> TestClient:
    # require_auth=False -> every caller is the anonymous, PUBLIC-clearance path.
    return TestClient(
        create_app(_engine(), _graph(), intelligence_store=_intel(tmp_path), require_auth=False)
    )


def _authed_client(tmp_path: Path) -> tuple[TestClient, AuthService]:
    service = AuthService(
        SqliteUserStore(f"sqlite:///{tmp_path / 'u.db'}"), secret="s", token_ttl_seconds=3600
    )
    client = TestClient(
        create_app(
            _engine(),
            _graph(),
            intelligence_store=_intel(tmp_path),
            auth_service=service,
            require_auth=True,
        )
    )
    return client, service


def _hdr(client: TestClient, service: AuthService, email: str, role: str) -> dict[str, str]:
    service.register(email, "password123", role=role)
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---- Anonymous callers see only PUBLIC content ------------------------------------


def test_anonymous_documents_list_excludes_private(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    ids = {d["canonical_id"] for d in client.get("/documents").json()}
    assert ids == {"pub1"}  # legit + restricted are withheld from anonymous


def test_anonymous_document_detail_private_is_404(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    assert client.get("/documents/pub1").status_code == 200
    # A private doc is indistinguishable from a missing one — no existence leak.
    assert client.get("/documents/priv1").status_code == 404
    assert client.get("/documents/legit1").status_code == 404


def test_anonymous_document_summary_private_is_404(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    assert client.get("/documents/pub1/summary").status_code == 200
    assert client.get("/documents/priv1/summary").status_code == 404


def test_anonymous_retrieve_excludes_private_evidence(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    # "sealed" appears ONLY in the private doc — anonymous retrieval must find nothing.
    body = client.post("/retrieve", json={"query": "sealed", "top_k": 5}).json()
    assert body["results"] == []
    ids = {r["canonical_id"] for r in client.post("/retrieve", json={"query": "acme", "top_k": 5}).json()["results"]}
    assert ids == {"pub1"}  # the corpus-wide query still only yields the public doc


def test_anonymous_answer_excludes_private(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    answer = client.get("/answer", params={"q": "sealed"}).json()["answer"]
    assert "Confidential" not in answer and "No evidence" in answer


def test_anonymous_compare_against_private_is_404(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    # Comparing two public docs would 404 on missing ids too, but a private id must
    # never be diffable by an anonymous caller.
    assert client.get("/compare", params={"a": "pub1", "b": "priv1"}).status_code == 404


def test_anonymous_graph_company_withholds_restricted_edges(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    body = client.get("/graph/company/acme").json()
    assert body["found"] is True
    relations = {n["relation"] for n in body["neighbors"]}
    assert relations == {"operates_in"}  # controlled_by (restricted) is withheld


def test_anonymous_entity_profile_withholds_restricted_edges(tmp_path: Path) -> None:
    client = _anon_client(tmp_path)
    acme = client.get("/entities/Company/acme").json()
    assert {r["relation"] for r in acme["relationships"]} == {"operates_in"}
    # The person on the restricted end must not surface the control relationship.
    jane = client.get("/entities/Person/jane").json()
    assert all(r["relation"] != "controlled_by" for r in jane["relationships"])


# ---- Authenticated callers keep compatible, tier-appropriate visibility ------------


def test_authenticated_analyst_sees_legitimate_interest_but_not_restricted(tmp_path: Path) -> None:
    client, service = _authed_client(tmp_path)
    hdr = _hdr(client, service, "ana@e.com", "analyst")
    ids = {d["canonical_id"] for d in client.get("/documents", headers=hdr).json()}
    assert ids == {"pub1", "legit1"}  # legitimate-interest now visible, restricted still not
    assert client.get("/documents/legit1", headers=hdr).status_code == 200
    assert client.get("/documents/priv1", headers=hdr).status_code == 404


def test_admin_sees_every_tier(tmp_path: Path) -> None:
    client, service = _authed_client(tmp_path)
    hdr = _hdr(client, service, "admin@e.com", "admin")
    ids = {d["canonical_id"] for d in client.get("/documents", headers=hdr).json()}
    assert ids == {"pub1", "legit1", "priv1"}
    assert client.get("/documents/priv1", headers=hdr).status_code == 200
    # Admin also sees the restricted control edge on the generic graph read.
    relations = {n["relation"] for n in client.get("/graph/company/acme", headers=hdr).json()["neighbors"]}
    assert "controlled_by" in relations


@pytest.mark.parametrize("route", ["/documents", "/graph/company/acme", "/entities/Company/acme"])
def test_public_routes_stay_reachable_anonymously(tmp_path: Path, route: str) -> None:
    # The guard filters CONTENT; it must not lock a public route (regression guard for
    # the closed-world public surface in tests/test_api_public.py).
    assert _anon_client(tmp_path).get(route).status_code == 200
