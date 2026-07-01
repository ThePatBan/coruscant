"""LEI providers: the swappable matcher behind the anchoring pipeline.

``LeiProvider`` is the seam. :class:`GleifApiProvider` hits GLEIF's free public API
(CC0 — commercially clean, no licence gate); :class:`LocalGleifProvider` scores
against a bundled/operator-supplied GLEIF export so CI is hermetic. Both propose
scored *candidates* with jurisdiction corroboration; the pipeline's per-kind
precision gate decides what is confirmed vs. left explicitly unresolved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from coruscant.knowledge_graph.textmatch import jurisdiction_country, normalize_name, org_score

_GLEIF_API = "https://api.gleif.org/api/v1"


class LeiRecord(BaseModel):
    """A candidate legal-entity record from GLEIF."""

    lei: str
    name: str
    country: str | None = None  # ISO-3166 alpha-2 of the legal address
    jurisdiction: str | None = None
    status: str | None = None  # entity/registration status (e.g. ACTIVE)
    registered_at: str | None = None  # ISO date of initial LEI registration
    other_names: list[str] = Field(default_factory=list)
    source_url: str | None = None

    def names(self) -> list[str]:
        seen: list[str] = []
        for candidate in (self.name, *self.other_names):
            if candidate and candidate not in seen:
                seen.append(candidate)
        return seen

    def is_active(self) -> bool:
        return (self.status or "").upper() == "ACTIVE"


class AnchorQuery(BaseModel):
    """One of our nodes to anchor (a Company or Subsidiary)."""

    kind: str
    key: str
    name: str
    jurisdiction: str | None = None  # Exhibit-21 jurisdiction, for corroboration


class AnchorMatch(BaseModel):
    """A candidate LEI match the provider surfaces; the pipeline gates it."""

    query: AnchorQuery
    record: LeiRecord
    score: float
    matched_name: str
    corroborated: bool  # the node's jurisdiction agrees with the record's country


class LeiProvider(Protocol):
    name: str

    def connected(self) -> bool: ...

    def resolve(self, queries: list[AnchorQuery]) -> list[AnchorMatch]: ...


def _corroborates(query: AnchorQuery, record: LeiRecord) -> bool:
    if not query.jurisdiction or not record.country:
        return False
    country = jurisdiction_country(query.jurisdiction)
    return country is not None and country == record.country.upper()


def _best_match(query: AnchorQuery, records: list[LeiRecord], floor: float) -> AnchorMatch | None:
    q_norm = normalize_name(query.name)
    if not q_norm:
        return None
    best: tuple[float, str, LeiRecord] | None = None
    for record in records:
        for original in record.names():
            score = org_score(q_norm, normalize_name(original))
            if best is None or score > best[0]:
                best = (score, original, record)
    if best is None or best[0] < floor:
        return None
    score, name, record = best
    return AnchorMatch(query=query, record=record, score=score, matched_name=name,
                       corroborated=_corroborates(query, record))


class LocalGleifProvider:
    """Offline provider scoring against a loaded GLEIF export. Hermetic (CI)."""

    name = "gleif-local"

    def __init__(self, records: list[LeiRecord], *, candidate_floor: float = 0.85) -> None:
        self._records = records
        self._floor = candidate_floor
        self._token_index: dict[str, set[int]] = {}
        self._norm_names: list[list[str]] = []
        for i, record in enumerate(records):
            normed = [normalize_name(n) for n in record.names()]
            self._norm_names.append(normed)
            for token in {tok for n in normed for tok in n.split()}:
                self._token_index.setdefault(token, set()).add(i)

    def connected(self) -> bool:
        return bool(self._records)

    def resolve(self, queries: list[AnchorQuery]) -> list[AnchorMatch]:
        matches: list[AnchorMatch] = []
        for query in queries:
            q_norm = normalize_name(query.name)
            candidate_ids: set[int] = set()
            for token in q_norm.split():
                candidate_ids |= self._token_index.get(token, set())
            candidates = [self._records[i] for i in candidate_ids]
            match = _best_match(query, candidates, self._floor)
            if match is not None:
                matches.append(match)
        matches.sort(key=lambda m: (-m.score, m.query.key, m.record.lei))
        return matches


class GleifApiProvider:
    """Live provider against GLEIF's public API (CC0). One lookup per query."""

    name = "gleif-api"

    def __init__(self, base_url: str = _GLEIF_API, *, candidate_floor: float = 0.85,
                 limit: int = 5, timeout: float = 20.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._floor = candidate_floor
        self._limit = limit
        self._timeout = timeout

    def connected(self) -> bool:
        try:
            req = Request(f"{self._base_url}/lei-records?page[size]=1",
                          headers={"Accept": "application/vnd.api+json"})
            with urlopen(req, timeout=min(self._timeout, 5.0)) as r:
                return 200 <= int(r.getcode()) < 300
        except Exception:
            return False

    def _lookup(self, name: str) -> list[LeiRecord]:
        url = (f"{self._base_url}/lei-records?filter[entity.legalName]={quote(name)}"
               f"&page[size]={self._limit}")
        req = Request(url, headers={"Accept": "application/vnd.api+json",
                                    "User-Agent": "Coruscant/0.1 (identity anchoring)"})
        try:
            with urlopen(req, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise RuntimeError(f"GLEIF lookup failed for {name!r}: {error}") from error
        return [_record_from_gleif(item) for item in payload.get("data", [])]

    def resolve(self, queries: list[AnchorQuery]) -> list[AnchorMatch]:
        matches: list[AnchorMatch] = []
        for query in queries:
            match = _best_match(query, self._lookup(query.name), self._floor)
            if match is not None:
                matches.append(match)
        matches.sort(key=lambda m: (-m.score, m.query.key, m.record.lei))
        return matches


def _record_from_gleif(item: dict[str, Any]) -> LeiRecord:
    attributes = item.get("attributes", {}) if isinstance(item, dict) else {}
    entity = attributes.get("entity", {}) or {}
    registration = attributes.get("registration", {}) or {}
    lei = str(attributes.get("lei") or item.get("id") or "")
    other_names = [n.get("name") for n in entity.get("otherNames", []) if isinstance(n, dict) and n.get("name")]
    reg_date = registration.get("initialRegistrationDate")
    return LeiRecord(
        lei=lei,
        name=str((entity.get("legalName") or {}).get("name") or ""),
        country=(entity.get("legalAddress") or {}).get("country"),
        jurisdiction=entity.get("jurisdiction"),
        status=entity.get("status") or registration.get("status"),
        registered_at=str(reg_date)[:10] if reg_date else None,
        other_names=[str(n) for n in other_names],
        source_url=f"https://search.gleif.org/#/record/{lei}" if lei else None,
    )


def load_gleif(path: Path) -> list[LeiRecord]:
    """Parse a GLEIF export: the API envelope ``{"data": [...]}``, a bare list of
    API items, or a list of simplified :class:`LeiRecord` dicts (fixtures)."""

    raw = json.loads(path.read_text())
    items = raw.get("data", []) if isinstance(raw, dict) else raw
    records: list[LeiRecord] = []
    for item in items:
        if isinstance(item, dict) and "attributes" in item:
            records.append(_record_from_gleif(item))
        else:
            records.append(LeiRecord.model_validate(item))
    return records
