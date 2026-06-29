"""Persisted ingestion run status for observability.

The worker / CLI writes a snapshot of the last ingestion run; the API exposes it
at ``/status`` so pipeline health, counts, and failures are observable without
scraping logs.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from coruscant.ingestion.orchestrator import IngestionReport


class RunStatus(BaseModel):
    completed_at: str
    document_count: int
    summary_count: int
    event_count: int
    change_set_count: int
    material_change_count: int
    companies: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @classmethod
    def from_report(cls, report: IngestionReport, *, completed_at: str) -> "RunStatus":
        return cls(
            completed_at=completed_at,
            document_count=report.document_count,
            summary_count=report.summary_count,
            event_count=report.event_count,
            change_set_count=report.change_set_count,
            material_change_count=report.material_change_count,
            companies=report.companies,
            source_types=report.source_types,
            errors=report.errors,
        )

    @property
    def ok(self) -> bool:
        return not self.errors


def save_status(status: RunStatus, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(status.model_dump_json(indent=2))


def load_status(path: Path) -> RunStatus | None:
    if not path.exists():
        return None
    return RunStatus.model_validate_json(path.read_text())
