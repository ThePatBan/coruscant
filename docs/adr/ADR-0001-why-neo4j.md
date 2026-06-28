# ADR-0001: Why Neo4j?

## Status

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
