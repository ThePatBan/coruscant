# Bootstrap Architecture

> **Status (2026-07-01):** this describes the original source-to-knowledge
> pipeline, which still holds — but it predates the portfolio-exposure product
> (the `/world` tab, the exposure engine, GICS/MSCI, instruments, live feeds).
> See [BUILD-STATE](../BUILD-STATE.md).

The bootstrap establishes a source-to-knowledge pipeline with explicit boundaries:

1. Fetch source data through a connector.
2. Persist immutable raw artifacts.
3. Normalize into typed document models.
4. Extract entities and relationships.
5. Project the result into the knowledge graph.
6. Optionally generate embeddings.
7. Index for search.
8. Support reasoning against normalized facts and provenance.

Company-specific logic is avoided. The tracked set — now **53 companies** (30 US Dow, 15 UK 20-F filers, 8 India ADRs) plus commodities and debt instruments — is driven from config (`companies.yml` / `instruments.yml`), not code.
