from __future__ import annotations

from coruscant.apps.runtime import run_ingestion
from coruscant.common.logging import configure_logging


def main() -> None:
    configure_logging()
    report = run_ingestion()
    print(
        f"Coruscant worker ingested {report.document_count} documents "
        f"across {len(report.companies)} companies and {len(report.source_types)} sources."
    )
    if report.errors:
        print(f"Encountered {len(report.errors)} errors.")


if __name__ == "__main__":
    main()
