# Components

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
| Knowledge graph | `knowledge_graph.*` | Project documents into nodes/edges; query and snapshot an in-memory graph (Neo4j is the intended production backend — ADR-0001). |
| Search | `search.*` | Deterministic hashing embeddings, an in-memory vector index, a lexical engine, and a `HybridRetrievalEngine` that blends both with evidence. |
| Persistence | `infrastructure.*` | Immutable filesystem artifacts for raw + normalized documents and a SQLite catalog (`database_url`) as the queryable read model. |
| Applications | `apps.*` | `runtime` wiring shared by the FastAPI `api`, the `cli`, and the `worker`. |

## Ports and adapters

Each capability is an abstract base or `Protocol` with at least one reference
implementation, so production backends can be substituted without touching the
core:

- `SourceConnector` → reference connectors + `EdgarHttpConnector`.
- `KnowledgeGraphStore` → `InMemoryKnowledgeGraphStore` (→ Neo4j later).
- `RetrievalEngine` → `InMemoryRetrievalEngine`, `HybridRetrievalEngine`.
- `RawDocumentRepository` / `NormalizedDocumentRepository` → filesystem adapters.
- `DocumentCatalog` (pipeline `Protocol`) → `SqliteDocumentCatalog` (→ PostgreSQL later).
