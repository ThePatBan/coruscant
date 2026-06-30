"""The LLM analyst — grounded, citation-enforced reasoning over the evidence.

Unlike the deterministic ReferenceAnalyst (which categorizes and echoes the
loudest fragments), this one *reasons*: it routes the platform's "complex" tier
to whatever model the admin configured (typically Opus), feeds it the denoised
change/event evidence, and asks for a short ranked thesis that synthesizes across
signals. The anti-fabrication guard is hard: every concern must cite evidence ids,
and any concern that cites nothing valid is dropped before it reaches the user —
so the model can reason, but it cannot invent.

Falls back to the deterministic analyst upstream when no model is configured.
"""

from __future__ import annotations

import json
import re

from coruscant.intelligence.analyst import AnalysisConcern, AnalysisReport, AnalysisStep
from coruscant.intelligence.confidence import MAX_CONFIDENCE
from coruscant.intelligence.models import ChangeSet, Claim, ExtractedEvent
from coruscant.llm import LLMError

_VALID_SEVERITY = {"high", "medium", "low"}
_OPPORTUNITY_RE = re.compile(r"\b(opportunit\w*|upside|bullish|tailwind\w*|catalyst\w*)\b")

_SYSTEM = """You are a forward-looking equity risk analyst at an investment research desk.
You reason ONLY over the numbered evidence provided. You never invent facts, figures, names, or events.

Produce a SHORT, ranked set of 3 to 5 distinct, non-overlapping concerns (or opportunities, if the focus
is opportunity) about the company over the next 6–12 months. SYNTHESIZE: connect signals into a thesis
(for example, how interest-rate moves, credit normalization, regulation, or guidance interact) rather than
restating a single sentence. Order by importance. Confidence is probabilistic — never 1.0.

Every concern MUST cite the evidence id(s) it is grounded in. If the evidence does not support a concern,
do not raise it.

Return STRICT JSON only — no prose, no markdown fences:
{"headline": "<one plain sentence>",
 "concerns": [
   {"title": "<3-6 words>",
    "category": "<guidance|regulatory|litigation|supply_chain|capital_allocation|executive|m&a|risk|product|opportunity>",
    "severity": "<high|medium|low>",
    "confidence": <number 0.0-0.95>,
    "rationale": "<1-2 sentences of synthesis>",
    "evidence_ids": [<int>, ...]}
 ]}"""


def _focus_of(question: str) -> str:
    return "opportunity" if _OPPORTUNITY_RE.search(question.lower()) else "risk"


def build_evidence(
    change_sets: list[ChangeSet], events: list[ExtractedEvent], *, limit: int = 40
) -> list[tuple[str, str, Claim]]:
    """The grounded evidence pool: material, categorized changes + events, deduped."""
    items: list[tuple[str, str, Claim]] = []
    for change_set in change_sets:
        if not change_set.material:
            continue
        for change in change_set.changes:
            if change.category == "general":
                continue  # uncategorized churn carries no thesis
            items.append((change.category, change.statement, change.evidence))
    for event in events:
        claim = Claim(
            text=event.description,
            source_uri=event.source_uri,
            section_title=event.section_title,
            canonical_id=event.canonical_id,
            category=event.category,
        )
        items.append((event.category, event.description, claim))

    seen: set[str] = set()
    pool: list[tuple[str, str, Claim]] = []
    for category, statement, claim in items:
        key = statement.strip()[:140].lower()
        if key in seen:
            continue
        seen.add(key)
        pool.append((category, statement, claim))
        if len(pool) >= limit:
            break
    return pool


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text.strip(), re.S)
    if not match:
        raise LLMError("Model did not return JSON.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}") from exc


class LLMAnalyst:
    def __init__(self, gateway, *, tier: str = "complex") -> None:
        self.gateway = gateway
        self.tier = tier

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
        evidence = build_evidence(change_sets, events)
        if not evidence:
            raise LLMError("No evidence available to reason over.")

        lines = [f"[{i + 1}] ({cat}) {text}" for i, (cat, text, _claim) in enumerate(evidence)]
        if country_exposures and focus == "risk":
            countries = sorted({country for country, _ in country_exposures})
            lines.append(f"[supply] Supplier/operational exposure to: {', '.join(countries)}.")
        user = (
            f"Company: {company_name}\nQuestion: {question}\nFocus: {focus}\n\n"
            "Evidence:\n" + "\n".join(lines)
        )

        result = self.gateway.complete(tier=self.tier, system=_SYSTEM, user=user, max_tokens=1500)
        data = _parse_json(result.text)

        concerns: list[AnalysisConcern] = []
        for raw in data.get("concerns", [])[:6]:
            if not isinstance(raw, dict):
                continue
            ids = [i for i in raw.get("evidence_ids", []) if isinstance(i, int) and 1 <= i <= len(evidence)]
            claims = [evidence[i - 1][2] for i in ids]
            if not claims:
                continue  # citation enforcement — a conclusion with no evidence is dropped
            severity = raw.get("severity")
            try:
                confidence = float(raw.get("confidence", 0.6))
            except (TypeError, ValueError):
                confidence = 0.6
            concerns.append(
                AnalysisConcern(
                    title=str(raw.get("title") or "Concern")[:70],
                    category=str(raw.get("category") or "risk"),
                    severity=severity if severity in _VALID_SEVERITY else "medium",
                    confidence=round(min(MAX_CONFIDENCE, max(0.0, confidence)), 2),
                    rationale=str(raw.get("rationale") or "").strip(),
                    evidence=claims,
                )
            )
        if not concerns:
            raise LLMError("Model produced no grounded concerns.")

        steps = [
            AnalysisStep(
                label="Model",
                detail=f"Reasoned with {result.model} via the {result.provider} provider "
                f"({result.latency_ms} ms).",
            ),
            AnalysisStep(
                label="Ground",
                detail=f"Constrained to {len(evidence)} cited evidence items; any conclusion without a "
                "citation was dropped.",
            ),
        ]
        headline = str(data.get("headline") or f"{company_name}: {len(concerns)} {focus} concern(s).")
        return AnalysisReport(
            company_slug=company_slug,
            company_name=company_name,
            question=question,
            focus=focus,
            headline=headline.strip(),
            steps=steps,
            concerns=concerns,
            generator=f"llm:{result.model}",
        )
