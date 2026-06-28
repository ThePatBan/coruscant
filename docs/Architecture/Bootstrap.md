# Bootstrap Architecture

The bootstrap establishes a source-to-knowledge pipeline with explicit boundaries:

1. Fetch source data through a connector.
2. Persist immutable raw artifacts.
3. Normalize into typed document models.
4. Extract entities and relationships.
5. Project the result into the knowledge graph.
6. Optionally generate embeddings.
7. Index for search.
8. Support reasoning against normalized facts and provenance.

Company-specific logic is avoided. Support for Apple, Microsoft, Tesla, ExxonMobil, Cargill, and SpaceX is driven from `config/companies.yml`.
