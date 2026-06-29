"""The AI Analyst — multi-step, deterministic, fully-cited reasoning.

Goes beyond single-shot retrieval: it searches, reads what changed and the
extracted events, reasons over them by category, compares the current disclosure
against the prior one, cites every conclusion, and answers with a structured set
of concerns. Confidence is always probabilistic (never certainty), and every
concern links to source evidence. A Claude-backed analyst can implement the same
interface (ADR-0004) without changing callers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from coruscant.intelligence.models import ChangeSet, Claim, ExtractedEvent

# Category -> (concern headline, severity, base confidence). Severity/confidence
# are deliberately bounded below certainty.
_CONCERN_RULES: dict[str, tuple[str, str, float]] = {
    "guidance": ("Forward guidance changed", "high", 0.72),
    "executive": ("Leadership change", "medium", 0.6),
    "regulatory": ("Regulatory exposure", "high", 0.72),
    "litigation": ("Legal / litigation exposure", "high", 0.7),
    "supply_chain": ("Supply-chain risk", "high", 0.7),
    "capital_allocation": ("Capital allocation shift", "medium", 0.58),
    "risk": ("New or heightened risk", "medium", 0.6),
    "m&a": ("M&A activity", "medium", 0.58),
    "product": ("Product / roadmap shift", "low", 0.5),
}
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_MAX_CONFIDENCE = 0.85  # never claim certainty


class AnalysisStep(BaseModel):
    label: str
    detail: str


class AnalysisConcern(BaseModel):
    title: str
    category: str
    severity: str
    confidence: float
    rationale: str
    evidence: list[Claim] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    company_slug: str
    company_name: str
    question: str
    focus: str  # "risk" | "opportunity"
    headline: str
    steps: list[AnalysisStep] = Field(default_factory=list)
    concerns: list[AnalysisConcern] = Field(default_factory=list)
    disclaimer: str = (
        "Probabilistic analysis derived from cited evidence — not investment advice "
        "and not a certainty. Every conclusion links to its source."
    )
    generator: str = "reference-analyst"


def _focus_of(question: str) -> str:
    lowered = question.lower()
    opportunity_cues = ("opportunit", "upside", "grow", "bull", "positive", "catalyst")
    if any(cue in lowered for cue in opportunity_cues):
        return "opportunity"
    return "risk"


class ReferenceAnalyst:
    def analyze(
        self,
        *,
        company_slug: str,
        company_name: str,
        question: str,
        change_sets: list[ChangeSet],
        events: list[ExtractedEvent],
        country_exposures: list[tuple[str, str]],
    ) -> AnalysisReport:
        focus = _focus_of(question)
        material = [cs for cs in change_sets if cs.material]
        steps = [
            AnalysisStep(
                label="Search",
                detail=f"Gathered {len(change_sets)} disclosure comparisons and "
                f"{len(events)} extracted events for {company_name}.",
            ),
            AnalysisStep(
                label="Read",
                detail=f"Read {len(material)} disclosures with material changes and "
                f"{len(country_exposures)} supply-chain country exposures.",
            ),
            AnalysisStep(
                label="Reason",
                detail="Classified each change and event by materiality category and "
                "weighted it by source.",
            ),
            AnalysisStep(
                label="Compare",
                detail="Each change is a diff of the current disclosure against the prior one.",
            ),
        ]

        concerns: list[AnalysisConcern] = []
        seen: set[tuple[str, str]] = set()

        # Reason over material changes (the strongest "what changed" signal).
        for change_set in material:
            for change in change_set.changes:
                rule = _CONCERN_RULES.get(change.category)
                if rule is None:
                    continue
                key = (change.category, change.statement[:60])
                if key in seen:
                    continue
                seen.add(key)
                title, severity, base = rule
                confidence = min(_MAX_CONFIDENCE, base + (0.05 if change.kind == "added" else 0.0))
                concerns.append(
                    AnalysisConcern(
                        title=title,
                        category=change.category,
                        severity=severity,
                        confidence=round(confidence, 2),
                        rationale=f"{change.kind.capitalize()} in {change_set.source_type}: "
                        f"{change.statement}",
                        evidence=[change.evidence],
                    )
                )

        # Geopolitical / supply exposure from the entity graph.
        countries = sorted({country for country, _ in country_exposures})
        for country in countries:
            suppliers = sorted({s for c, s in country_exposures if c == country})
            concerns.append(
                AnalysisConcern(
                    title=f"Geopolitical exposure to {country}",
                    category="supply_chain",
                    severity="medium",
                    confidence=0.55,
                    rationale=f"{company_name} depends on {', '.join(suppliers)} operating in "
                    f"{country}, creating concentration/geopolitical exposure.",
                    evidence=[
                        Claim(
                            text=f"{company_name} relies on {', '.join(suppliers)} in {country}.",
                            source_uri="reference-entities",
                            section_title="entity graph",
                            category="supply_chain",
                        )
                    ],
                )
            )

        concerns.sort(key=lambda c: (_SEVERITY_RANK.get(c.severity, 9), -c.confidence))

        steps.append(
            AnalysisStep(
                label="Cite",
                detail=f"Attached source evidence to all {len(concerns)} concerns.",
            )
        )
        steps.append(AnalysisStep(label="Answer", detail="Synthesized the assessment below."))

        headline = self._headline(company_name, question, focus, concerns)
        return AnalysisReport(
            company_slug=company_slug,
            company_name=company_name,
            question=question,
            focus=focus,
            headline=headline,
            steps=steps,
            concerns=concerns,
        )

    def _headline(
        self, company_name: str, question: str, focus: str, concerns: list[AnalysisConcern]
    ) -> str:
        if not concerns:
            return f"No material {focus} signals found for {company_name} in the available evidence."
        high = sum(1 for c in concerns if c.severity == "high")
        lead = concerns[0].title.lower()
        return (
            f"{company_name}: {len(concerns)} evidence-backed concern(s) "
            f"({high} high-severity), led by {lead}."
        )
