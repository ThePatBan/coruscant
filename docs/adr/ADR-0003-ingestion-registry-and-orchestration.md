# ADR-0003: Ingestion Registry and Orchestration

## Status

Accepted

## Context

ADR-0002 established the monorepo and source contracts. The bootstrap shipped a
single hard-coded SEC EDGAR pipeline, ingestion did not feed search, and there
was no way to run the lifecycle across the configured companies and sources. To
reach an end-to-end MVP we need a way to add sources by configuration and to run
every source through one consistent lifecycle.

## Decision

Introduce a `SourceRegistry` of `SourceDefinition` entries (source type → label,
document type, connector factory, normalizer) and a single
`GenericIngestionPipeline` that wires every lifecycle stage. An
`IngestionOrchestrator` runs the pipeline across companies (`companies.yml`) ×
enabled sources (`sources.yml`) and returns a structured `IngestionReport`.

Reference connectors synthesize deterministic, evidence-bearing sample documents
so the full pipeline runs offline; live connectors (e.g. `EdgarHttpConnector`)
remain the production path behind the same `SourceConnector` port.

A SQLite catalog (`SqliteDocumentCatalog`, via `database_url`) is the queryable
read model, and the knowledge graph is snapshotted to JSON so the API can load a
corpus without re-running ingestion.

## Consequences

- New sources are added by registering a `SourceDefinition`; no core changes.
- Ingestion now feeds the graph, embeddings, retrieval, and the catalog.
- Pipelines run independently and are togglable per source via config.
- The catalog and graph snapshot give the API a durable read model; both ports
  can later target PostgreSQL/pgvector and Neo4j without a rewrite.
- Reference connectors produce sample data — clearly marked
  `provenance: reference-sample` — and are not a substitute for live sources.

## Alternatives Considered

- One bespoke pipeline class per source (duplication, drift).
- A plugin/entry-point discovery mechanism (more machinery than the MVP needs).
- Serving directly from in-memory state with no persistence (no decoupling of
  ingestion from serving).

## Date

2026-06-28
