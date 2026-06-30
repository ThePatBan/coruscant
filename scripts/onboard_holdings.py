"""Fetch recent Form 4 insider holdings for the configured companies and project
``Company -insider_holding-> Person {shares}`` edges into the graph snapshot.

This is the holdings layer. It is a network step (SEC EDGAR), deliberately kept
out of the offline extraction pass, and run after the companies + 10-Ks are
onboarded:

    SSL_CERT_FILE=$(python3 -m certifi) CORUSCANT_CONFIG_DIR=deploy/dow-config \\
      CORUSCANT_DATA_DIR=data python3 scripts/onboard_holdings.py --limit 25

People are keyed by name, so an insider who is already an officer/director (parsed
from the 10-K) gets a holding attached in place rather than duplicated.
"""

from __future__ import annotations

import argparse

from coruscant.common.config import Settings, load_companies
from coruscant.connectors.sec_edgar import fetch_recent_form4_holdings
from coruscant.knowledge_graph.extraction import project_holdings_edges
from coruscant.knowledge_graph.persistence import load_graph, save_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="recent Form 4s to scan per company")
    args = parser.parse_args()

    settings = Settings()
    store = load_graph(settings.graph_snapshot_path)
    companies = load_companies(settings.config_dir)

    total = 0
    for company in companies:
        if not company.cik:
            print(f"  ! {company.slug:5} no CIK — skipping", flush=True)
            continue
        holdings = fetch_recent_form4_holdings(
            company.cik, user_agent=settings.edgar_user_agent, limit=args.limit
        )
        projected = project_holdings_edges(store, company.slug, holdings)
        total += projected
        print(f"  + {company.slug:5} {projected:3} insider holdings", flush=True)

    save_graph(store, settings.graph_snapshot_path)
    print(f"\nProjected {total} insider_holding edges; snapshot saved to {settings.graph_snapshot_path}")


if __name__ == "__main__":
    main()
