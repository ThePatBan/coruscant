"""Screening providers: the swappable matcher behind the pipeline.

``ScreeningProvider`` is the seam. :class:`DeterministicScreeningProvider` is the
PR-1 implementation — pure-stdlib name normalization + token blocking + a
conservative deterministic score, so the whole spine runs in CI with no service
and no network. :class:`YenteScreeningProvider` marks the PR-2 seam where
OpenSanctions' ``yente`` (nomenklatura's scorer, at scale) plugs in over HTTP.

*Why deterministic and conservative:* a false-positive PEP hit on a customer's
counterparty is a defamation/discrimination exposure, not a data blip (§4.3). The
provider only proposes *candidates* with a score; the pipeline's precision gate
decides what is confirmed vs. routed to human review.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

# OpenSanctions topic codes → our two edge classes.
_SANCTION_PREFIX = "sanction"
_PEP_PREFIXES = ("role.pep", "role.rca")  # rca = relatives & close associates


def normalize_name(name: str) -> str:
    """Fold to a comparable form: strip diacritics (NFKD), casefold, keep only
    alphanumeric tokens, collapse whitespace. Romanization is a *recall* aid — the
    native-script original stays canonical on the node (Invariant #3)."""

    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", stripped.casefold()))


def _tokens(normalized: str) -> set[str]:
    return set(normalized.split())


def _score(a: str, b: str) -> float:
    """Conservative similarity of two normalized names in [0, 1]."""

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = _tokens(a), _tokens(b)
    if ta == tb:  # same tokens, different order ("john smith" vs "smith john")
        return 0.98
    union = ta | tb
    jaccard = len(ta & tb) / len(union) if union else 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return round(0.5 * jaccard + 0.5 * ratio, 4)


class ScreeningQuery(BaseModel):
    """One entity of ours to screen (typically a ``Person`` node)."""

    kind: str
    key: str
    name: str
    source: str | None = None  # how it entered our graph (e.g. sec-form4 vs officers)
    country: str | None = None
    birth_date: str | None = None


class WatchlistRecord(BaseModel):
    """A candidate authority record (OpenSanctions / FollowTheMoney shape)."""

    id: str
    name: str
    schema_: str = Field(default="Person", alias="schema")
    topics: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    birth_date: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    source_url: str | None = None
    aliases: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def names(self) -> list[str]:
        seen: list[str] = []
        for candidate in (self.name, *self.aliases):
            if candidate and candidate not in seen:
                seen.append(candidate)
        return seen

    def is_sanctioned(self) -> bool:
        return any(t == _SANCTION_PREFIX or t.startswith(_SANCTION_PREFIX + ".") for t in self.topics)

    def is_pep(self) -> bool:
        return any(topic.startswith(prefix) for topic in self.topics for prefix in _PEP_PREFIXES)


class ScreeningMatch(BaseModel):
    """A candidate match the provider surfaces; the pipeline gates it."""

    query: ScreeningQuery
    record: WatchlistRecord
    score: float
    matched_name: str
    corroborated: bool  # a second attribute (country / birth year) also agreed


class ScreeningProvider(Protocol):
    """The swappable matcher. ``connected()`` reports whether a dataset/service is
    wired (so the API can show an honest ``connected: false`` stub when it is not)."""

    name: str

    def connected(self) -> bool: ...

    def screen(self, queries: list[ScreeningQuery]) -> list[ScreeningMatch]: ...


def _country_norm(value: str) -> str:
    return normalize_name(value)


def _corroborates(query: ScreeningQuery, record: WatchlistRecord) -> bool:
    """Whether a discriminator beyond the name agrees — the difference between a
    real hit and a common-name collision ("Wang Wei")."""

    if query.country and record.countries:
        q = _country_norm(query.country)
        if q and q in {_country_norm(c) for c in record.countries}:
            return True
    if query.birth_date and record.birth_date:
        if query.birth_date[:4] == record.birth_date[:4]:  # birth year
            return True
    return False


class DeterministicScreeningProvider:
    """Zero-dependency name matcher: block by shared token, score, keep candidates
    above ``candidate_floor``. Deterministic and auditable — the same query always
    yields the same candidates."""

    name = "deterministic-name-v1"

    def __init__(self, records: list[WatchlistRecord], *, candidate_floor: float = 0.85) -> None:
        self._records = records
        self._floor = candidate_floor
        self._by_id = {r.id: r for r in records}
        # Normalized names per record + an inverted token index for blocking.
        self._norm_names: dict[str, list[str]] = {}
        self._token_index: dict[str, set[str]] = {}
        for record in records:
            normed = [normalize_name(n) for n in record.names()]
            self._norm_names[record.id] = normed
            for token in {tok for n in normed for tok in n.split()}:
                self._token_index.setdefault(token, set()).add(record.id)

    def connected(self) -> bool:
        return bool(self._records)

    def screen(self, queries: list[ScreeningQuery]) -> list[ScreeningMatch]:
        matches: list[ScreeningMatch] = []
        for query in queries:
            q_norm = normalize_name(query.name)
            if not q_norm:
                continue
            candidate_ids: set[str] = set()
            for token in _tokens(q_norm):
                candidate_ids |= self._token_index.get(token, set())
            for record_id in candidate_ids:
                record = self._by_id[record_id]
                best_name = ""
                best_score = 0.0
                for original, normed in zip(record.names(), self._norm_names[record_id]):
                    score = _score(q_norm, normed)
                    if score > best_score:
                        best_score, best_name = score, original
                if best_score >= self._floor:
                    matches.append(
                        ScreeningMatch(
                            query=query, record=record, score=best_score,
                            matched_name=best_name, corroborated=_corroborates(query, record),
                        )
                    )
        # Deterministic order: strongest first, then stable by ids.
        matches.sort(key=lambda m: (-m.score, m.query.key, m.record.id))
        return matches


class YenteScreeningProvider:
    """PR-2 seam: OpenSanctions' ``yente`` (nomenklatura's scorer) over HTTP, run
    as a Docker sidecar so its heavy deps (ICU, scikit-learn, Elasticsearch) stay
    out of this process. Implemented in PR 2; the interface is fixed here so the
    pipeline and graph model do not change when it lands."""

    name = "yente"

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def connected(self) -> bool:
        return False  # not wired until PR 2

    def screen(self, queries: list[ScreeningQuery]) -> list[ScreeningMatch]:
        raise NotImplementedError(
            "YenteScreeningProvider lands in PR 2 (yente Docker sidecar over HTTP)."
        )


def load_opensanctions(path: Path) -> list[WatchlistRecord]:
    """Parse an OpenSanctions export into :class:`WatchlistRecord` s.

    Accepts either the bulk newline-delimited ``targets.nested.json`` or a plain
    JSON array (used by fixtures). Only the fields we screen on are read; the raw
    FollowTheMoney ``properties`` shape (lists per field) is flattened."""

    text = path.read_text().strip()
    if not text:
        return []
    rows: list[dict[str, object]]
    if text[0] == "[":
        rows = json.loads(text)
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [_record_from(row) for row in rows]


def _first(value: object) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    if value is None:
        return None
    return str(value)


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def _record_from(row: dict[str, object]) -> WatchlistRecord:
    props = row.get("properties")
    props = props if isinstance(props, dict) else {}
    names = _as_list(props.get("name"))
    caption = _first(row.get("caption"))
    primary = names[0] if names else (caption or str(row.get("id", "")))
    aliases = [n for n in (*names, *_as_list(props.get("alias"))) if n and n != primary]
    record_id = str(row.get("id", ""))
    return WatchlistRecord(
        id=record_id,
        name=primary,
        schema=str(row.get("schema", "Person")),
        topics=_as_list(props.get("topics")),
        datasets=_as_list(row.get("datasets")),
        countries=_as_list(props.get("country")),
        birth_date=_first(props.get("birthDate")),
        first_seen=_first(row.get("first_seen")),
        last_seen=_first(row.get("last_seen")),
        source_url=f"https://www.opensanctions.org/entities/{record_id}/" if record_id else None,
        aliases=aliases,
    )
