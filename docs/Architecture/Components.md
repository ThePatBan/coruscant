# Components

> **Status (2026-07-01):** the graph store is **JSON-over-SQLite** (Neo4j was
> never built — [ADR-0001](../adr/ADR-0001-why-neo4j.md)), and this list predates
> the **exposure engine** (GICS/MSCI/commodity/debt pathways), the GICS/MSCI
> **taxonomy** + **instrument** model, and the free gated **live feeds**
> (`pricing` / `macro` / `news`). See [BUILD-STATE](../BUILD-STATE.md).

The MVP is a single Python package (`coruscant`) organized into ports (abstract
interfaces) and reference adapters. Source-specific behavior lives in connectors;
everything else is generic.

## Layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Configuration | `common.config` | Load companies (`companies.yml`) and sources (`sources.yml`), expose `Settings`. |
| Domain models | `common.types` | `SourceDocument`, `NormalizedDocument`, `DocumentSection`, `EvidenceSpan`, `GraphNode`, `GraphEdge`. |
| Connectors | `connectors.*` | Fetch + normalize per source. SEC EDGAR has a live HTTP connector; all seven sources have an offline reference connector. |
| Registry | `ingestion.registry` | Map a `source_type` to its connector factory + normalizer (`SourceDefinition`). The extension point for new pipelines. |
| Pipeline | `ingestion.pipeline` | `GenericIngestionPipeline` runs the lifecycle: fetch → store raw → normalize → project graph → embed → index → catalog. |
| Orchestrator | `ingestion.orchestrator` | Run the pipeline across companies × enabled sources and emit an `IngestionReport`. |
| Knowledge graph | `knowledge_graph.*` | Project documents + curated taxonomy/instruments into nodes/edges; the exposure-engine queries; snapshot an in-memory graph to a JSON file (a real graph store is a future step — ADR-0001). |
| Search | `search.*` | Deterministic hashing embeddings, an in-memory vector index, a lexical engine, and a `HybridRetrievalEngine` that blends both with evidence. |
| Persistence | `infrastructure.*` | Immutable filesystem artifacts for raw + normalized documents and a SQLite catalog (`database_url`) as the queryable read model. |
| Applications | `apps.*` | `runtime` wiring shared by the FastAPI `api`, the `cli`, and the `worker`. |

## Ports and adapters

Each capability is an abstract base or `Protocol` with at least one reference
implementation, so production backends can be substituted without touching the
core:

- `SourceConnector` → reference connectors + `EdgarHttpConnector`.
- `KnowledgeGraphStore` → `InMemoryKnowledgeGraphStore` (JSON snapshot; a real graph store TBD).
- `RetrievalEngine` → `InMemoryRetrievalEngine`, `HybridRetrievalEngine`.
- `RawDocumentRepository` / `NormalizedDocumentRepository` → filesystem adapters.
- `DocumentCatalog` (pipeline `Protocol`) → `SqliteDocumentCatalog` (→ PostgreSQL later).
