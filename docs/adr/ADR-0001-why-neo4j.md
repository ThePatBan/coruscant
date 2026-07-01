# ADR-0001: Why Neo4j?

## Status

**Superseded / aspirational (2026-07-01) — Neo4j was never implemented.** The
shipping store is **JSON-over-SQLite**: an in-process `InMemoryKnowledgeGraphStore`
persisted to `data/graph/graph.json`, alongside SQLite for the catalog /
intelligence / users / embeddings. This ADR records the original intent and the
requirements a graph store must meet; it does **not** describe the current system
(see [../BUILD-STATE.md](../BUILD-STATE.md)).

A real graph store remains the acknowledged next foundational step before
whole-exchange ingestion — but the **vendor is undecided** (Neo4j is one option,
not a committed choice). Where other docs cite "Neo4j as the graph backend," read
that as this open, future decision, not a built component.

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
