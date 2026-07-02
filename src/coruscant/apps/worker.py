from __future__ import annotations

from coruscant.apps.runtime import run_ingestion, seed_demo_user
from coruscant.apps.workspace_runtime import evaluate_all_watchlists
from coruscant.common.logging import configure_logging


def main() -> None:
    configure_logging()
    # The worker is the scheduled lifecycle: ingest only what is due, then
    # evaluate watchlists so notifications are generated with no user action.
    report = run_ingestion(respect_due=True)
    seed_demo_user()
    notifications = evaluate_all_watchlists()
    print(
        f"Coruscant worker ingested {report.document_count} documents "
        f"across {len(report.companies)} companies and {len(report.source_types)} sources "
        f"({report.material_change_count} material change sets); "
        f"generated {notifications} watchlist notification(s)."
    )
    if report.errors:
        print(f"Encountered {len(report.errors)} errors.")


if __name__ == "__main__":
    main()
