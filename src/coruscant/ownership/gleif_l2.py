"""GLEIF Level 2 ("who owns whom") — accounting consolidation as an auxiliary signal.

GLEIF publishes, alongside the Level-1 reference data the anchoring pipeline already
uses, **Level-2 relationship records**: a legal entity's *direct* and *ultimate
accounting-consolidating parent*. That is an **accounting-consolidation** claim, and
nothing more — GLEIF L2 is explicitly *not* a %-ownership figure — so it maps to the
``consolidates`` edge only, keeping it distinct from declared shareholding and
beneficial ownership (architecture §2.4). It is an *auxiliary control/identity
signal*, never a substitute for a real ownership disclosure.

This module parses GLEIF's relationship-record JSON into
:class:`OwnershipRecord`\\ s of basis ``ACCOUNTING_CONSOLIDATION`` and exposes them
through the existing :class:`OwnershipProvider` seam — so the ownership pipeline
reconciles them by LEI against already-anchored nodes (enrich, don't duplicate),
dedups edges on identity (idempotent re-runs), and never overwrites an existing
anchor. In GLEIF a relationship reads *start-node IS_CONSOLIDATED_BY end-node*, i.e.
the **end node is the parent**; we record ``holder = parent → subject = child``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from coruscant.ownership.models import (
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
)

GLEIF_L2_SOURCE = "gleif-l2"
_GLEIF_API = "https://api.gleif.org/api/v1"
# The two consolidation relationship types GLEIF L2 exposes. Both are accounting
# consolidation (not ownership %); "direct" is one level, "ultimate" is the top.
_DIRECT = "IS_DIRECTLY_CONSOLIDATED_BY"
_ULTIMATE = "IS_ULTIMATELY_CONSOLIDATED_BY"


def _lei_party(lei: str, name: str | None) -> OwnershipParty:
    lei = lei.strip().upper()
    return OwnershipParty(
        name=(name or lei).strip() or lei,
        kind="Company",
        anchor=PartyAnchor(scheme="lei", value=lei) if lei else None,
    )


def _period_bounds(periods: Any) -> tuple[str | None, str | None]:
    """The accounting-relationship validity window from ``relationshipPeriods``,
    preferring the ACCOUNTING period; open-ended bounds stay ``None`` (never faked)."""

    if not isinstance(periods, list):
        return None, None
    chosen: dict[str, Any] | None = None
    for period in periods:
        if not isinstance(period, dict):
            continue
        ptype = str(period.get("periodType") or "").upper()
        if ptype == "ACCOUNTING_PERIOD":
            chosen = period
            break
        if chosen is None:
            chosen = period
    if chosen is None:
        return None, None
    start = str(chosen.get("startDate") or "").strip()[:10] or None
    end = str(chosen.get("endDate") or "").strip()[:10] or None
    return start, end


def _record_from_relationship(attrs: dict[str, Any]) -> OwnershipRecord | None:
    """One GLEIF relationship-record ``attributes`` object → a consolidation
    :class:`OwnershipRecord`, or ``None`` when it is not a consolidation relationship
    or is missing an endpoint (never a fabricated half-edge)."""

    rel = attrs.get("relationship")
    if not isinstance(rel, dict):
        return None
    rel_type = str(rel.get("relationshipType") or "").strip().upper()
    if rel_type not in (_DIRECT, _ULTIMATE):
        return None  # only consolidation relationships become `consolidates` edges
    start_node = rel.get("startNode") or {}
    end_node = rel.get("endNode") or {}
    child_lei = str(start_node.get("id") or "").strip().upper()  # start IS_CONSOLIDATED_BY end
    parent_lei = str(end_node.get("id") or "").strip().upper()   # → end node is the parent
    if not child_lei or not parent_lei:
        return None
    status = str(rel.get("relationshipStatus") or "").strip().upper()
    if status and status not in ("ACTIVE", "PUBLISHED", "NULL"):
        return None  # only currently-in-force relationships (LAPSED/INACTIVE skipped)
    valid_from, valid_to = _period_bounds(rel.get("relationshipPeriods"))
    return OwnershipRecord(
        holder=_lei_party(parent_lei, None),
        subject=_lei_party(child_lei, None),
        basis=OwnershipBasis.ACCOUNTING_CONSOLIDATION,
        interest=("ultimate-consolidation" if rel_type == _ULTIMATE else "direct-consolidation"),
        source=GLEIF_L2_SOURCE,
        source_url=f"https://search.gleif.org/#/record/{child_lei}",
        valid_from=valid_from, valid_to=valid_to,
    )


def _relationship_items(data: Any) -> list[dict[str, Any]]:
    """The relationship-record items from GLEIF's ``{"data": [...]}`` envelope, a bare
    list, or a single ``{"data": {...}}`` (a direct/ultimate-parent-relationship
    endpoint returns one record)."""

    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            return [i for i in inner if isinstance(i, dict)]
        if isinstance(inner, dict):
            return [inner]
        return []
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    return []


def parse_gleif_relationships(text: str) -> list[OwnershipRecord]:
    """Parse GLEIF relationship-record JSON into consolidation
    :class:`OwnershipRecord`\\ s. Accepts the API envelope, a bare list, NDJSON, or a
    single record; non-consolidation and dangling entries are skipped, never faked."""

    stripped = text.strip()
    if not stripped:
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        records: list[OwnershipRecord] = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.extend(_records_from_payload(obj))
        return records
    return _records_from_payload(data)


def _records_from_payload(data: Any) -> list[OwnershipRecord]:
    out: list[OwnershipRecord] = []
    seen: set[tuple[str, str]] = set()
    for item in _relationship_items(data):
        attrs = item.get("attributes") if isinstance(item, dict) else None
        if not isinstance(attrs, dict):
            continue
        record = _record_from_relationship(attrs)
        if record is None:
            continue
        # Dedup within a payload: the same (parent, child) can appear as both a
        # direct and an ultimate relationship — keep the first (direct wins by order).
        parent = record.holder.anchor.value if record.holder.anchor else record.holder.name
        child = record.subject.anchor.value if record.subject.anchor else record.subject.name
        key = (parent, child)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


class GleifL2ConsolidationProvider:
    """Accounting-consolidation records from GLEIF Level-2 relationship data.

    Live path: construct with the ``leis`` to look up (typically the graph's already-
    anchored LEIs) and each entity's direct/ultimate consolidating parent is pulled
    from GLEIF's CC0 API. Operator fallback: ``from_file`` parses a downloaded
    relationship-record export. Hermetic in CI via injected ``text`` — no network."""

    name = GLEIF_L2_SOURCE
    market = "*"  # LEI is a global key; consolidation is not market-specific

    def __init__(
        self,
        *,
        leis: list[str] | None = None,
        base_url: str = _GLEIF_API,
        text: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._leis = [str(x).strip().upper() for x in (leis or []) if str(x).strip()]
        self._base_url = base_url.rstrip("/")
        self._text = text
        self._timeout = timeout

    @classmethod
    def from_file(cls, path: Path, **kwargs: Any) -> "GleifL2ConsolidationProvider":
        return cls(text=Path(path).read_text(), **kwargs)

    def connected(self) -> bool:
        return self._text is not None or bool(self._leis)

    def _get(self, path: str) -> dict[str, Any]:
        req = Request(
            f"{self._base_url}/{path}",
            headers={"Accept": "application/vnd.api+json",
                     "User-Agent": "Coruscant/0.1 (L2 consolidation)"},
        )
        try:
            with urlopen(req, timeout=self._timeout) as response:  # noqa: S310 (trusted GLEIF host)
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 — surface as an explicit runtime failure
            raise RuntimeError(f"GLEIF L2 fetch failed for {path!r}: {error}") from error
        return payload if isinstance(payload, dict) else {}

    def list_ownership(self) -> list[OwnershipRecord]:
        if self._text is not None:
            return parse_gleif_relationships(self._text)
        records: list[OwnershipRecord] = []
        seen: set[tuple[str, str]] = set()
        for lei in self._leis:
            for rel in ("direct-parent-relationship", "ultimate-parent-relationship"):
                try:
                    payload = self._get(f"lei-records/{quote(lei)}/{rel}")
                except RuntimeError:
                    continue  # a missing parent is a 404 → no relationship, not an error
                for record in _records_from_payload(payload):
                    parent = record.holder.anchor.value if record.holder.anchor else record.holder.name
                    child = record.subject.anchor.value if record.subject.anchor else record.subject.name
                    if (parent, child) in seen:
                        continue
                    seen.add((parent, child))
                    records.append(record)
        return records
