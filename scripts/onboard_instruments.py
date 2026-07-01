"""Project the non-equity instrument inventory (commodities + debt) into the
graph snapshot — offline, no re-fetch, preserving every other edge.

A full re-ingest also projects instruments (``extract_relationships`` now takes
them), but rebuilds from scratch and would drop the network-fetched holdings
layer. So this layers instruments onto the persisted snapshot in place:

    CORUSCANT_DATA_DIR=data CORUSCANT_CONFIG_DIR=deploy/dow-config \\
      python3 scripts/onboard_instruments.py

Idempotent: prior Commodity/DebtInstrument/Sector nodes and their edges are
dropped first, then re-projected from instruments.yml.
"""

from __future__ import annotations

from coruscant.common.config import Settings, load_instruments
from coruscant.knowledge_graph.extraction import project_instrument_edges
from coruscant.knowledge_graph.persistence import load_graph, save_graph

_DROP_RELATIONS = {"affects_sector", "issued_by"}
_DROP_NODE_KINDS = {"Commodity", "DebtInstrument", "Sector"}


def main() -> None:
    settings = Settings()
    store = load_graph(settings.graph_snapshot_path)
    instruments = load_instruments(settings.config_dir)

    # Drop only debt-derived Country nodes (created by this projector); keep any
    # Country nodes another projector owns.
    debt_countries = {edge.target_key for edge in store.edges_by_relation("issued_by")}
    store.edges = [edge for edge in store.edges if edge.relation not in _DROP_RELATIONS]
    store.nodes = {
        key: node
        for key, node in store.nodes.items()
        if node.kind not in _DROP_NODE_KINDS
        and not (node.kind == "Country" and node.key in debt_countries and node.properties.get("source") == "debt-inventory")
    }

    counts = project_instrument_edges(store, instruments)
    save_graph(store, settings.graph_snapshot_path)
    print(
        f"Projected {counts['commodities']} commodities and {counts['debt']} debt instruments.\n"
        f"Snapshot saved to {settings.graph_snapshot_path}"
    )


if __name__ == "__main__":
    main()
