"""Re-tag the graph snapshot's sector layer to GICS and add MSCI market-tier
edges — offline, no re-fetch, preserving every other edge (holdings, people,
subsidiaries, co-mentions).

A full re-ingest would also be correct (``extract_relationships`` now projects
GICS + market tiers), but it rebuilds from scratch and would drop the network-
fetched ``insider_holding`` layer that ``onboard_holdings.py`` adds afterwards. So
this script edits the persisted snapshot in place instead:

    CORUSCANT_DATA_DIR=data CORUSCANT_CONFIG_DIR=deploy/dow-config \\
      python3 scripts/recompute_taxonomy.py

It is idempotent: the old SIC ``Industry`` nodes + ``in_sector`` edges (and any
prior ``MarketTier`` / ``in_market_tier``) are dropped first, then re-projected
from the curated taxonomy, so a re-run converges. Company nodes are refreshed so
they carry ``gics_sector`` / ``market_tier``.
"""

from __future__ import annotations

from coruscant.common.config import Settings, load_companies
from coruscant.knowledge_graph.extraction import (
    project_company_nodes,
    project_market_tier_edges,
    project_sector_edges,
)
from coruscant.knowledge_graph.persistence import load_graph, save_graph

_DROP_RELATIONS = {"in_sector", "in_market_tier"}
_DROP_NODE_KINDS = {"Industry", "MarketTier"}


def main() -> None:
    settings = Settings()
    store = load_graph(settings.graph_snapshot_path)
    companies = load_companies(settings.config_dir)

    before_edges, before_nodes = len(store.edges), len(store.nodes)
    # Drop the old taxonomy layer so the re-projection fully replaces it.
    store.edges = [edge for edge in store.edges if edge.relation not in _DROP_RELATIONS]
    store.nodes = {key: node for key, node in store.nodes.items() if node.kind not in _DROP_NODE_KINDS}

    project_company_nodes(store, companies)  # refresh gics_sector / market_tier props
    sectors = project_sector_edges(store, companies)
    tiers = project_market_tier_edges(store, companies)

    save_graph(store, settings.graph_snapshot_path)
    sub_industries = sum(1 for node in store.nodes.values() if node.kind == "Industry")
    distinct_sectors = len(
        {
            str(edge.properties.get("sector"))
            for edge in store.edges_by_relation("in_sector")
            if edge.properties.get("sector")
        }
    )
    print(
        f"Re-tagged {sectors} in_sector edges to {sub_industries} GICS sub-industries "
        f"across {distinct_sectors} sectors; projected {tiers} in_market_tier edges.\n"
        f"Nodes {before_nodes} -> {len(store.nodes)}, edges {before_edges} -> {len(store.edges)}.\n"
        f"Snapshot saved to {settings.graph_snapshot_path}"
    )


if __name__ == "__main__":
    main()
