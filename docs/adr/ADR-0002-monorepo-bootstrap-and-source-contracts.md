# ADR-0002: Monorepo Bootstrap and Source Contracts

## Status

Accepted

## Context

Coruscant needs a maintainable foundation for source ingestion, normalization, graph projection, and search without locking the system to a single vendor or data provider.

## Decision

Establish a Python monorepo with a shared `src/coruscant` package and separate modules for apps, connectors, graph abstractions, infrastructure ports, and common data models.

Use configuration files for company-specific behavior and define source contracts that every new pipeline must satisfy.

## Consequences

- New data sources can be added without changing core domain models.
- Pipelines can be executed independently.
- The repository can evolve toward PostgreSQL, pgvector, Neo4j, and task orchestration without a rewrite.

## Alternatives Considered

- Single application module with ad hoc integrations.
- Vendor-specific implementations with hard-coded company logic.

## Date

2026-06-28
