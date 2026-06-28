# Data Flow

The platform turns raw source material into queryable, evidence-bearing
intelligence through one fixed lifecycle. Every source travels the same path;
only the connector and normalizer differ.

## Ingestion lifecycle

```
config (companies.yml + sources.yml)
        │
        ▼
IngestionOrchestrator ── for each company × enabled source ──▶ GenericIngestionPipeline
        │
        ▼
   1. fetch          SourceConnector.fetch(FetchRequest) ─▶ SourceDocument (raw, immutable)
   2. store_raw      RawDocumentRepository (data/raw/<source_type>/<hash>.json)
   3. normalize      normalizer(SourceDocument) ─▶ NormalizedDocument (sections + evidence)
   4. project_graph  ReferenceGraphProjector ─▶ GraphNode/GraphEdge ─▶ KnowledgeGraphStore
   5. embed          HashingEmbedder ─▶ vector ─▶ HybridRetrievalEngine
   6. index          retrieval engine + NormalizedDocumentRepository
   7. catalog        SqliteDocumentCatalog (queryable read model)
        │
        ▼
   IngestionReport (counts, per-source totals, errors)
   graph snapshot ─▶ data/graph/graph.json
```

## Provenance chain

Provenance is preserved end to end. A `NormalizedDocument` keeps its
`source_uri` and `canonical_id`; every `DocumentSection` carries `EvidenceSpan`s
that point back to the source and section; graph nodes/edges record
`source_canonical_id` and `source_uri`; and retrieval results return the
originating excerpt. A `/retrieve` answer can always be traced to the section and
source it came from.

## Query / read path

```
API startup (lifespan) ─▶ load_engine() from SQLite catalog
                       └▶ load_graph_store() from graph snapshot

GET  /retrieve   ─▶ HybridRetrievalEngine.retrieve_with_evidence ─▶ answer + evidence
GET  /documents  ─▶ catalog-backed read model
GET  /graph/...  ─▶ KnowledgeGraphStore.neighbors
```

The read model is rebuilt from durable stores, so the API serves the same
corpus the worker produced — ingestion and serving are decoupled.
