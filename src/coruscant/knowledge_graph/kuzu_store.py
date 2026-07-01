"""Kùzu-backed knowledge graph store.

Kùzu is an embedded, disk-based, columnar property-graph database (the "DuckDB of
graph"): free (MIT), no server, and native Cypher. It is the on-ramp to the
Cypher end state — the same queries repoint at Neo4j / Neptune later with a driver
change, not a rewrite. See docs/adr/ADR-0001 and the store-vendor decision.

Model (deliberately generic, so the schema never migrates as new node kinds /
relations appear): a single ``Node`` table keyed by ``kind\x1fkey`` and a single
``Edge`` rel table. Every node/edge's ``properties`` dict — including the
provenance ``source`` on every edge — is carried verbatim as a JSON string, so
the statement-based provenance invariant round-trips faithfully.

An integer ``seq`` column records insertion order on both tables and every list
query is ``ORDER BY seq``, so this store reproduces the in-memory store's
insertion-order semantics exactly (that parity is asserted by the golden test).

Two usage modes:
- *writable* (``:memory:`` for tests, or a path) — build via :meth:`from_dict` or
  incremental ``upsert_*``. Bulk load runs in a single transaction (per-statement
  autocommit fsyncs every write and is ~18x slower).
- *read-only* (:meth:`open_synced`) — the serving path opens an on-disk DB built
  from the JSON snapshot, rebuilding it only when the snapshot is newer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import kuzu

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph.store import KnowledgeGraphStore

_ID_SEP = "\x1f"  # unit separator: never appears in a node kind/key


def _nid(kind: str, key: str) -> str:
    return f"{kind}{_ID_SEP}{key}"


def _dumps(properties: dict[str, Any]) -> str:
    # Preserve original key order: EntityProfile.properties is serialized in dict
    # order, so the served JSON must match the in-memory store key-for-key.
    return json.dumps(properties)


class KuzuKnowledgeGraphStore(KnowledgeGraphStore):
    def __init__(self, db_path: str = ":memory:", *, read_only: bool = False) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(db_path, read_only=read_only)
        self._conn = kuzu.Connection(self._db)
        self._read_only = read_only
        if not read_only:
            self._ensure_schema()
        # Continue the insertion-order counter from what's already persisted.
        self._node_seq = self._max_seq("Node")
        self._edge_seq = self._max_seq("Edge")

    # -- schema / setup -------------------------------------------------------

    def _ensure_schema(self) -> None:
        tables = {row[0] for row in self._rows("CALL show_tables() RETURN name")}
        if "Node" not in tables:
            self._conn.execute(
                "CREATE NODE TABLE Node("
                "id STRING, kind STRING, ekey STRING, props STRING, seq INT64, "
                "PRIMARY KEY(id))"
            )
        if "Edge" not in tables:
            self._conn.execute(
                "CREATE REL TABLE Edge(FROM Node TO Node, relation STRING, props STRING, seq INT64)"
            )

    def _max_seq(self, table: str) -> int:
        pattern = "(n:Node)" if table == "Node" else "()-[n:Edge]->()"
        row = self._rows(f"MATCH {pattern} RETURN max(n.seq)")
        value = row[0][0] if row else None
        return int(value) + 1 if value is not None else 0

    # -- query helpers --------------------------------------------------------

    def _rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[Any]:
        # A fresh connection per call keeps concurrent reads thread-safe (FastAPI
        # runs sync endpoints in a threadpool) without serializing on one cursor.
        conn = kuzu.Connection(self._db)
        result = conn.execute(cypher, params or {})
        if isinstance(result, list):  # execute() unions to a list for multi-statement
            result = result[0]
        out: list[Any] = []
        while result.has_next():
            out.append(result.get_next())
        return out

    @staticmethod
    def _edge(row: list[Any]) -> GraphEdge:
        sk, skey, rel, tk, tkey, props = row[0], row[1], row[2], row[3], row[4], row[5]
        return GraphEdge(
            source_kind=sk, source_key=skey, relation=rel,
            target_kind=tk, target_key=tkey, properties=json.loads(props),
        )

    _EDGE_RETURN = (
        "a.kind, a.ekey, e.relation, b.kind, b.ekey, e.props"
    )

    # -- writes ---------------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> None:
        # Last-write-wins on (kind, key), matching the in-memory store; seq is set
        # only on first creation so insertion order is stable across re-upserts.
        self._conn.execute(
            "MERGE (n:Node {id:$id}) "
            "ON CREATE SET n.kind=$kind, n.ekey=$key, n.props=$props, n.seq=$seq "
            "ON MATCH SET n.props=$props",
            {"id": _nid(node.kind, node.key), "kind": node.kind, "key": node.key,
             "props": _dumps(node.properties), "seq": self._node_seq},
        )
        self._node_seq += 1

    def upsert_edge(self, edge: GraphEdge) -> None:
        # First-write-wins on the full (source, relation, target) identity — an
        # existing edge keeps its original provenance (ON CREATE SET only).
        self._conn.execute(
            "MATCH (a:Node {id:$sid}), (b:Node {id:$tid}) "
            "MERGE (a)-[e:Edge {relation:$rel}]->(b) "
            "ON CREATE SET e.props=$props, e.seq=$seq",
            {"sid": _nid(edge.source_kind, edge.source_key),
             "tid": _nid(edge.target_kind, edge.target_key),
             "rel": edge.relation, "props": _dumps(edge.properties), "seq": self._edge_seq},
        )
        self._edge_seq += 1

    # -- reads ----------------------------------------------------------------

    def get_node(self, kind: str, key: str) -> GraphNode | None:
        rows = self._rows(
            "MATCH (n:Node {id:$id}) RETURN n.kind, n.ekey, n.props",
            {"id": _nid(kind, key)},
        )
        if not rows:
            return None
        r = rows[0]
        return GraphNode(kind=r[0], key=r[1], properties=json.loads(r[2]))

    def nodes_of_kind(self, kind: str) -> list[GraphNode]:
        rows = self._rows(
            "MATCH (n:Node {kind:$kind}) RETURN n.kind, n.ekey, n.props ORDER BY n.seq",
            {"kind": kind},
        )
        return [GraphNode(kind=r[0], key=r[1], properties=json.loads(r[2])) for r in rows]

    def outgoing(self, kind: str, key: str) -> list[GraphEdge]:
        rows = self._rows(
            f"MATCH (a:Node {{id:$id}})-[e:Edge]->(b:Node) RETURN {self._EDGE_RETURN} ORDER BY e.seq",
            {"id": _nid(kind, key)},
        )
        return [self._edge(r) for r in rows]

    def incoming(self, kind: str, key: str) -> list[GraphEdge]:
        rows = self._rows(
            f"MATCH (a:Node)-[e:Edge]->(b:Node {{id:$id}}) RETURN {self._EDGE_RETURN} ORDER BY e.seq",
            {"id": _nid(kind, key)},
        )
        return [self._edge(r) for r in rows]

    def edges_by_relation(self, relation: str) -> list[GraphEdge]:
        rows = self._rows(
            f"MATCH (a:Node)-[e:Edge {{relation:$rel}}]->(b:Node) RETURN {self._EDGE_RETURN} ORDER BY e.seq",
            {"rel": relation},
        )
        return [self._edge(r) for r in rows]

    def all_nodes(self) -> list[GraphNode]:
        rows = self._rows("MATCH (n:Node) RETURN n.kind, n.ekey, n.props ORDER BY n.seq")
        return [GraphNode(kind=r[0], key=r[1], properties=json.loads(r[2])) for r in rows]

    def all_edges(self) -> list[GraphEdge]:
        rows = self._rows(
            f"MATCH (a:Node)-[e:Edge]->(b:Node) RETURN {self._EDGE_RETURN} ORDER BY e.seq"
        )
        return [self._edge(r) for r in rows]

    def reachable(
        self, kind: str, key: str, relation: str, max_hops: int, *, direction: str = "any"
    ) -> dict[tuple[str, str], int]:
        # Native variable-length SHORTEST path, filtering each hop to `relation` —
        # the multi-hop traversal the flat store couldn't do at scale. Overrides
        # the port's BFS default; the golden test asserts they return the same set
        # + distances. `hops` is an int (cast), so interpolating it is injection-safe.
        hops = max(1, int(max_hops))
        left, right = {"out": ("-", "->"), "in": ("<-", "-"), "any": ("-", "-")}[direction]
        cypher = (
            f"MATCH (a:Node {{id:$id}}){left}"
            f"[e:Edge* SHORTEST 1..{hops} (r, n | WHERE r.relation = $rel)]"
            f"{right}(b:Node) RETURN b.kind, b.ekey, length(e)"
        )
        out: dict[tuple[str, str], int] = {}
        for row in self._rows(cypher, {"id": _nid(kind, key), "rel": relation}):
            node_key, hop = (row[0], row[1]), int(row[2])
            if node_key == (kind, key):
                continue
            if node_key not in out or hop < out[node_key]:
                out[node_key] = hop
        return out

    def node_count(self) -> int:
        rows = self._rows("MATCH (n:Node) RETURN count(*)")
        return int(rows[0][0]) if rows else 0

    def edge_count(self) -> int:
        rows = self._rows("MATCH ()-[e:Edge]->() RETURN count(*)")
        return int(rows[0][0]) if rows else 0

    # -- bulk load / lifecycle ------------------------------------------------

    def _bulk_load(self, data: dict[str, Any]) -> None:
        """Load a to_dict() snapshot in one transaction. Replicates the in-memory
        store's dedup semantics (nodes last-write-wins, edges first-write-wins)
        in O(N+E) so the two backends hold byte-identical graphs."""
        nodes: dict[str, tuple[int, GraphNode]] = {}
        for raw in data.get("nodes", []):
            node = GraphNode.model_validate(raw)
            nid = _nid(node.kind, node.key)
            seq = nodes[nid][0] if nid in nodes else len(nodes)
            nodes[nid] = (seq, node)  # keep first seq, latest value
        edges: dict[tuple[str, str, str, str, str], tuple[int, GraphEdge]] = {}
        for raw in data.get("edges", []):
            edge = GraphEdge.model_validate(raw)
            ident = (edge.source_kind, edge.source_key, edge.relation,
                     edge.target_kind, edge.target_key)
            if ident in edges:
                continue  # first-write-wins
            edges[ident] = (len(edges), edge)

        conn = self._conn
        conn.execute("BEGIN TRANSACTION")
        try:
            for nid, (seq, node) in nodes.items():
                conn.execute(
                    "CREATE (n:Node {id:$id, kind:$kind, ekey:$key, props:$props, seq:$seq})",
                    {"id": nid, "kind": node.kind, "key": node.key,
                     "props": _dumps(node.properties), "seq": seq},
                )
            for seq, edge in edges.values():
                conn.execute(
                    "MATCH (a:Node {id:$sid}), (b:Node {id:$tid}) "
                    "CREATE (a)-[:Edge {relation:$rel, props:$props, seq:$seq}]->(b)",
                    {"sid": _nid(edge.source_kind, edge.source_key),
                     "tid": _nid(edge.target_kind, edge.target_key),
                     "rel": edge.relation, "props": _dumps(edge.properties), "seq": seq},
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        self._node_seq = len(nodes)
        self._edge_seq = len(edges)

    @classmethod
    def from_dict(cls, data: dict[str, Any], db_path: str = ":memory:") -> "KuzuKnowledgeGraphStore":
        store = cls(db_path)
        store._bulk_load(data)
        return store

    @classmethod
    def open_synced(cls, db_path: str, json_path: Path) -> "KuzuKnowledgeGraphStore":
        """Serving entrypoint: return a read-only store at ``db_path``, rebuilding
        it from the JSON snapshot iff the DB is missing or older than the snapshot.
        Ingestion still writes the JSON snapshot; the Kùzu DB is the queryable,
        disk-persistent materialization of it."""
        db = Path(db_path)
        stale = (not db.exists()) or (
            json_path.exists() and json_path.stat().st_mtime > db.stat().st_mtime
        )
        if stale:
            cls._rebuild(db_path, json_path)
        return cls(db_path, read_only=True)

    @classmethod
    def _rebuild(cls, db_path: str, json_path: Path) -> None:
        # Single-writer/local model: rebuild in place. (A temp-file swap is the
        # hardening for concurrent multi-worker serving.)
        db = Path(db_path)
        db.parent.mkdir(parents=True, exist_ok=True)
        for p in (db, Path(f"{db_path}.wal")):
            if p.exists():
                p.unlink()
        data = json.loads(json_path.read_text()) if json_path.exists() else {"nodes": [], "edges": []}
        builder = cls(db_path)
        builder._bulk_load(data)
        builder.close()  # checkpoint the WAL into the main file before serving reads

    def close(self) -> None:
        # Dropping the connection + database handle flushes/checkpoints on GC.
        self._conn = None  # type: ignore[assignment]
        self._db = None  # type: ignore[assignment]
