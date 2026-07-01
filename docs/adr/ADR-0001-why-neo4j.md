# ADR-0001: Why Neo4j?

## Status

**Superseded by the store-vendor decision (2026-07-01).** Neo4j was never
implemented. The serving graph store is now **Kùzu** — an embedded, disk-based,
Cypher-native property-graph DB (free/MIT, no server) — behind the stable
`KnowledgeGraphStore` port. SQLite continues to hold the catalog / intelligence /
users / embeddings.

**Why Kùzu now, not Neo4j:** the end state still leans Cypher (Neo4j Aura or
Amazon Neptune for managed HA / RBAC / graph-algorithms at scale), but standing up
and paying for a server graph DB against a ~1k-node graph is premature. Kùzu gives
the **same operational profile as SQLite** (a file, zero ops) *and* is the only
free/embedded option that is natively built for the multi-hop `owns*` / `supplies*`
ownership traversals the product needs. Because Kùzu speaks Cypher, the migration
to Neo4j/Neptune for public deployment is a **driver + connection-string change,
not a query rewrite** — we write the query layer against Cypher once. The
`KnowledgeGraphStore` port keeps the engine swappable; `graph_backend="memory"`
retains the in-process prototype as the test double + golden-parity comparator.

**End-state path (deferred, not rejected):** Neo4j Aura / Amazon Neptune when
public deployment demands managed HA, RBAC (to enforce the `access_tier`
invariant), online backup, and graph-data-science at scale. The requirements
below still apply to that engine.

_Original decision, retained for context:_

Accepted

## Context

Coruscant needs a knowledge system that can represent entities, relationships, provenance, and propagation pathways explicitly.
The project is centered on explainability and traceable reasoning rather than opaque inference.

## Decision

Use Neo4j as the primary graph database for the knowledge and relationship layer.

## Consequences

- Relationships can be modeled directly rather than flattened into application logic.
- Query patterns for provenance and propagation become more explicit.
- The graph model can support future ontology and reasoning work.
- The system accepts a graph-specific operational dependency.

## Alternatives Considered

- Relational-only storage
- Document-only storage
- Postgres with graph-like tables only

## Date

2026-06-28
