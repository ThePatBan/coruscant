"""Knowledge graph abstractions — the shared, domain-neutral graph substrate.

Boundary: PLATFORM primitive — see docs/PLATFORM.md §7. Owns the ``KnowledgeGraphStore``
port and backends (in-memory / Kùzu), persistence, entity resolution, the bitemporal +
access-tier substrate, text matching, and the reference projectors. The workspace-domain
graph logic (exposure queries, GICS/MSCI taxonomy, entity + ingestion projection, UBO
traversals) was extracted to ``coruscant.exposure`` in Phase 3 (docs/PLATFORM.md §9, seam 3).
"""
