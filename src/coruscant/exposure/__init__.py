"""Portfolio-Exposure workspace — graph domain logic.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7, §9 (seam 3).

Phase 3 of the platform/workspace split (ADR-0013) physically extracts the
investment-domain graph logic out of the platform ``knowledge_graph`` substrate into
this workspace package. It owns:

- ``queries`` — the exposure engine (geographic/sector/market-tier/commodity/debt
  pathways, entity profiles, co-executive + network reads);
- ``ownership_graph`` — UBO chain-following and group/contagion traversals;
- ``taxonomy`` — the GICS / MSCI classification tables;
- ``entities`` — company-entity node projection (suppliers/customers/…);
- ``extraction`` — ingestion-time projection of the investment universe into the graph.

Everything here depends on the platform ``knowledge_graph`` store port and substrate —
never the reverse. ``knowledge_graph`` is now a domain-neutral graph substrate.
"""
