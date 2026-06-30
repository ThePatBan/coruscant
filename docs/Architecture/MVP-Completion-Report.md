# MVP Completion Report

> **Historical snapshot (2026-06-28).** This records the initial MVP build and is
> **superseded by the M2–M5 work** that landed afterward. Its metrics are point-in-
> time and now stale (e.g. "8 endpoints / 54 tests / 45 modules" → the code now has
> ~58 routes / 268 tests / ~85 modules). For current scope and verified milestone
> status see [docs/roadmap/Milestones.md](../roadmap/Milestones.md) and
> [docs/api/Contract.md](../api/Contract.md). Do not treat the counts below as live.

**Date:** 2026-06-28
**Scope:** Complete the Coruscant MVP build on top of the bootstrap architecture.

## Summary

The repository began as a well-structured *bootstrap* — interfaces plus a single
SEC EDGAR reference path, with 11 passing tests but several pieces that did not
yet connect into a working system. The MVP build closes those gaps: the platform
now runs the full `fetch → store → normalize → graph → embed → index → reason`
lifecycle, config-driven, across all seven in-scope sources and six companies,
queryable through a CLI and an API, with provenance preserved end to end.

Final state: **45 source modules / ~2,820 LOC**, **54 tests passing**, `ruff`
clean, `mypy` clean (strict `disallow_untyped_defs`). `make setup`, `make test`,
`make lint`, and `make api` all work.

## Gaps found in the bootstrap

1. **Ingestion did not feed search.** `IngestionPipeline.project_and_index` was
   dead code; normalized documents were written to disk but never indexed, so the
   API's `/retrieve` served an empty engine.
2. **Only 1 of 7 sources** had a connector.
3. **No orchestration** across companies × sources; the worker only printed a count.
4. **No persistence/load path** — `database_url` and SQLAlchemy were configured but unused.
5. **No embeddings / vector search** — `create_embeddings` was a no-op.
6. **Thin API/CLI** — no company/document/graph endpoints; the CLI was a demo function.
7. **`make lint` was red** — 8 pre-existing `mypy` errors.

## What was built

| Area | Delivered |
| --- | --- |
| Type/lint baseline | Fixed 8 `mypy` errors, removed dead `project_and_index`, added `types-PyYAML`. `make lint` is green. |
| Source registry | `SourceRegistry` / `SourceDefinition` + `default_registry()` — add a source by registration only. |
| Generic pipeline | `GenericIngestionPipeline` wires every lifecycle stage; optional collaborators are skipped cleanly. |
| Connectors | Reference connectors + normalizers for investor relations, earnings calls, press releases, job postings, news, patents, plus a `ReferenceEdgarConnector`. |
| Embeddings & search | Deterministic `HashingEmbedder`, `InMemoryVectorIndex`, and `HybridRetrievalEngine` blending lexical + vector with evidence. |
| Knowledge graph | Queryable in-memory store (`neighbors`, `nodes_of_kind`, dedup), JSON snapshot persistence, document-type-aware node kinds/relations. |
| Persistence | `SqliteDocumentCatalog` (SQLAlchemy) as the queryable read model; filesystem repositories keep immutable raw + normalized artifacts. |
| Orchestration | `IngestionOrchestrator` over companies × enabled sources → `IngestionReport`; `apps.runtime` shared wiring. |
| Applications | API with 8 endpoints loading the persisted corpus on startup; full `coruscant` CLI (`companies/sources/ingest/query/graph/serve`) via console script; worker runs ingestion. |
| Config | `config/sources.yml`, `edgar_user_agent` + `graph_snapshot_path` settings, `load_sources`. |
| Docs | Filled `Components.md` and `Data Flow.md`, added ADR-0003, updated README, this report. |

## Verification

- **Tests:** 54 passing (`pytest`), up from 11. Covers connectors, registry,
  embeddings, hybrid search, catalog, graph store/persistence, generic pipeline,
  orchestrator, runtime end-to-end, CLI, and all API endpoints.
- **Static checks:** `ruff check src tests` clean; `mypy src` clean.
- **End-to-end run:** `coruscant ingest` produces 42 documents (6 companies × 7
  sources), a 94-node graph, and persisted artifacts (raw + normalized JSON,
  SQLite catalog, graph snapshot). `coruscant query` and every API endpoint
  return evidence-bearing results against the persisted corpus.

## Design fidelity

The build honors the stated design rules: raw data is immutable, normalized
facts are separate from raw documents, every section and graph element carries
provenance back to its source, source-specific behavior is confined to
connectors/config, and all sources share one lifecycle. Reference connectors are
explicitly marked `provenance: reference-sample` and exist only to exercise the
pipeline offline.

## Not in this MVP (recommended next)

- **Live connectors** for the six non-SEC sources (the ports exist; only the
  reference adapters ship).
- **Production backends** behind the existing ports: PostgreSQL/pgvector for the
  catalog and embeddings, Neo4j for the graph (ADR-0001).
- **Real entity resolution and relationship extraction** (today the projector
  derives Company/Document/Section structure; richer extraction is a hook point).
- **LLM-backed reasoning** to replace the template reasoning layer.
- **Incremental/scheduled ingestion** and deduplication across runs (the catalog
  upsert is idempotent per document; orchestration is currently a full sweep).
- **A real embedding model** behind the `HashingEmbedder` interface.
