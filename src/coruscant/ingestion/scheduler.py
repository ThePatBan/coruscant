"""Ingestion scheduler — decides which sources are due for re-ingestion.

Pure, deterministic due-calculation (testable with an injected ``now``) over each
source's cadence and last successful run. The worker uses this to ingest only
what is due rather than re-pulling everything every tick.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from coruscant.ingestion.registry import SourceDefinition


def is_due(last_run_iso: str | None, cadence_days: int, now: datetime) -> bool:
    if last_run_iso is None:
        return True  # never ingested
    try:
        last = datetime.fromisoformat(last_run_iso)
    except ValueError:
        return True
    return (now - last) >= timedelta(days=cadence_days)


def due_sources(
    definitions: list[SourceDefinition],
    last_runs: dict[str, str],
    now: datetime,
) -> list[str]:
    """Source types whose cadence has elapsed since their last successful run."""

    return [
        definition.source_type
        for definition in definitions
        if is_due(last_runs.get(definition.source_type), definition.cadence_days, now)
    ]
