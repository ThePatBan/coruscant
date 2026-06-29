"""Predictive signals — probabilistic, evidence-backed, never certain.

Derives forward-looking signals (emerging risk, supply-chain stress, hiring,
patent momentum, capital-allocation trend, geopolitical exposure, management
confidence) from what has already been observed and cited. Each signal has a
direction, a bounded strength (a probability, not a prediction), and source
evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.models import ChangeSet, Claim, ExtractedEvent

_MAX_STRENGTH = 0.8  # signals are probabilistic, never certain


class Signal(BaseModel):
    type: str
    company_slug: str
    label: str
    direction: str  # "up" | "down" | "elevated" | "easing" | "neutral"
    strength: float
    rationale: str
    evidence: list[Claim] = Field(default_factory=list)


def _doc_claim(document: NormalizedDocument) -> Claim:
    return Claim(
        text=document.title or document.document_type,
        source_uri=document.source_uri,
        section_title=None,
        canonical_id=document.canonical_id,
    )


class ReferenceSignalEngine:
    def signals_for(
        self,
        *,
        company_slug: str,
        company_name: str,
        documents: list[NormalizedDocument],
        change_sets: list[ChangeSet],
        events: list[ExtractedEvent],
        country_exposures: list[tuple[str, str]],
    ) -> list[Signal]:
        by_type: dict[str, list[NormalizedDocument]] = {}
        for document in documents:
            by_type.setdefault(document.document_type, []).append(document)

        material_changes = [c for cs in change_sets if cs.material for c in cs.changes]
        signals: list[Signal] = []

        def add(type_: str, label: str, direction: str, strength: float, rationale: str, evidence: list[Claim]) -> None:
            signals.append(
                Signal(
                    type=type_,
                    company_slug=company_slug,
                    label=label,
                    direction=direction,
                    strength=round(min(_MAX_STRENGTH, strength), 2),
                    rationale=rationale,
                    evidence=evidence,
                )
            )

        # Management confidence — from guidance direction.
        guidance = [c for c in material_changes if c.category == "guidance"]
        if guidance:
            lowered = any("lower" in c.statement.lower() or "soft" in c.statement.lower() for c in guidance)
            add(
                "management_confidence",
                "Management confidence",
                "down" if lowered else "up",
                0.62 if lowered else 0.55,
                f"Guidance language {'weakened' if lowered else 'held/strengthened'} in the latest disclosure.",
                [guidance[0].evidence],
            )

        # Emerging risk — added risk / regulatory / litigation changes.
        risk_changes = [c for c in material_changes if c.category in {"risk", "regulatory", "litigation"} and c.kind == "added"]
        if risk_changes:
            add(
                "emerging_risk",
                "Emerging risk",
                "elevated",
                0.55 + 0.05 * min(3, len(risk_changes)),
                f"{len(risk_changes)} new risk/regulatory/legal disclosure(s) versus the prior period.",
                [c.evidence for c in risk_changes[:3]],
            )

        # Supply-chain stress — supply_chain changes and/or concentration.
        sc_changes = [c for c in material_changes if c.category == "supply_chain"]
        if sc_changes or country_exposures:
            evidence = [c.evidence for c in sc_changes[:2]]
            countries = sorted({c for c, _ in country_exposures})
            if countries and not evidence:
                evidence = [
                    Claim(
                        text=f"{company_name} relies on suppliers in {', '.join(countries)}.",
                        source_uri="reference-entities",
                        section_title="entity graph",
                        category="supply_chain",
                    )
                ]
            add(
                "supply_chain_stress",
                "Supply-chain stress",
                "elevated",
                0.5 + 0.05 * len(countries) + (0.1 if sc_changes else 0.0),
                "Supplier-related changes and/or country concentration in the supply chain.",
                evidence,
            )

        # Hiring — presence of job postings.
        jobs = by_type.get("job_posting", [])
        if jobs:
            add(
                "hiring",
                "Hiring activity",
                "up",
                0.5,
                f"{len(jobs)} active job posting(s) signal investment in capacity.",
                [_doc_claim(jobs[0])],
            )

        # Patent momentum.
        patents = by_type.get("patent", [])
        if patents:
            add(
                "patent_momentum",
                "Patent momentum",
                "up",
                0.5,
                f"{len(patents)} patent record(s) indicate ongoing R&D output.",
                [_doc_claim(patents[0])],
            )

        # Capital allocation trend.
        capital = [c for c in material_changes if c.category == "capital_allocation"]
        if capital:
            add(
                "capital_allocation",
                "Capital allocation trend",
                "elevated",
                0.55,
                "Capital-allocation language changed versus the prior disclosure.",
                [capital[0].evidence],
            )

        # Geopolitical exposure.
        if country_exposures:
            countries = sorted({c for c, _ in country_exposures})
            add(
                "geopolitical",
                "Geopolitical exposure",
                "elevated",
                0.5 + 0.05 * len(countries),
                f"Supply chain spans {', '.join(countries)}.",
                [
                    Claim(
                        text=f"{company_name} is exposed to {', '.join(countries)} via its suppliers.",
                        source_uri="reference-entities",
                        section_title="entity graph",
                        category="supply_chain",
                    )
                ],
            )

        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals
