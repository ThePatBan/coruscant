from coruscant.intelligence.llm_analyst import LLMAnalyst
from coruscant.intelligence.models import ChangeSet, Claim, DocumentChange
from coruscant.llm.gateway import LLMResult


class _FakeGateway:
    """A gateway whose complete() returns a fixed payload (no network)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.last_user = ""

    def complete(self, *, tier: str, system: str, user: str, max_tokens: int = 1024) -> LLMResult:
        self.last_user = user
        return LLMResult(text=self.text, tier=tier, provider="fake", model="claude-opus-4-8", latency_ms=12)


def _change(category: str, statement: str) -> DocumentChange:
    return DocumentChange(
        kind="added",
        category=category,
        statement=statement,
        confidence=0.6,
        evidence=Claim(text=statement, source_uri="u", canonical_id="c", category=category),
    )


def _change_set() -> ChangeSet:
    return ChangeSet(
        company_slug="jpm",
        source_type="sec_edgar",
        current_canonical_id="c1",
        changes=[
            _change("regulatory", "The Firm is subject to Basel III endgame capital requirements."),
            _change("guidance", "Net interest income is sensitive to the pace of Federal Reserve rate changes."),
        ],
    )


def test_llm_analyst_grounds_and_drops_uncited_concerns() -> None:
    payload = (
        '{"headline":"JPMorgan: rate + capital pressure.","concerns":['
        '{"title":"NII compression","category":"guidance","severity":"high","confidence":0.99,'
        '"rationale":"Faster Fed cuts compress net interest income.","evidence_ids":[2]},'
        '{"title":"Ungrounded claim","category":"risk","severity":"high","confidence":0.8,'
        '"rationale":"no citation","evidence_ids":[]},'
        '{"title":"Bad citation","category":"risk","severity":"low","confidence":0.5,'
        '"rationale":"out of range","evidence_ids":[99]}]}'
    )
    gateway = _FakeGateway(payload)
    report = LLMAnalyst(gateway).analyze(
        company_slug="jpm",
        company_name="JPMorgan Chase & Co",
        question="Why should I worry over the next six months?",
        change_sets=[_change_set()],
        events=[],
        country_exposures=[],
    )

    # Only the cited concern survives; ungrounded and out-of-range citations are dropped.
    assert [c.title for c in report.concerns] == ["NII compression"]
    assert report.concerns[0].confidence < 1.0  # never certainty
    assert report.concerns[0].evidence[0].text.startswith("Net interest income")
    assert report.generator == "llm:claude-opus-4-8"
    # The evidence really was handed to the model.
    assert "Basel III endgame" in gateway.last_user
