"""JSON snapshot persistence for the in-memory knowledge graph.

The graph is rebuilt on every ingestion run and snapshotted to disk (this JSON) so
the API can load it without re-running ingestion. The JSON is also the portable,
backend-neutral form the serving Kùzu store is materialized from — see
:func:`coruscant.apps.runtime.load_graph_store` and
:class:`coruscant.knowledge_graph.kuzu_store.KuzuKnowledgeGraphStore` (and ADR-0001
for the Kùzu-now / Neo4j-later store decision). Both stay behind the same
:class:`KnowledgeGraphStore` port.
"""

from __future__ import annotations

import json
from pathlib import Path

from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore


def save_graph(store: InMemoryKnowledgeGraphStore, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store.to_dict(), indent=2))


def load_graph(path: Path) -> InMemoryKnowledgeGraphStore:
    if not path.exists():
        return InMemoryKnowledgeGraphStore()
    data = json.loads(path.read_text())
    return InMemoryKnowledgeGraphStore.from_dict(data)
