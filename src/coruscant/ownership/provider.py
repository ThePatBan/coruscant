"""Ownership providers: the swappable feed behind the ownership pipeline.

``OwnershipProvider`` is the seam (mirroring ``coverage`` / ``screening`` /
``anchoring``). :class:`StaticOwnershipProvider` replays a fixed record list so CI
is hermetic. :class:`BodsOwnershipProvider` parses the **Beneficial Ownership Data
Standard** (BODS) — the format OpenOwnership publishes and UK PSC exports map to —
which is *natively statement-based* (every fact carries its source), the reference
implementation of Invariant #1.

The BODS parser is honesty-preserving: a person interested-party becomes a
``beneficial_owner`` claim; an entity interested-party a ``declared_shareholding``;
a percentage is read only where the ``share`` is stated (an exact figure, or a
disclosed min/max *band* — never invented). Accounting *consolidation* is a
different claim from a different source (GLEIF L2), so it is NOT synthesized here —
it arrives as its own :class:`OwnershipBasis`, keeping the three edge types
distinct (architecture §2.4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from coruscant.ownership.models import (
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
)

BODS_SOURCE = "openownership-bods"


class OwnershipProvider(Protocol):
    """The ownership feed seam, deliberately market-plural (mirroring
    ``CoverageProvider``). ``market`` is an ISO-3166 alpha-2 (``GB``) or ``*`` for a
    market-agnostic source (BODS can carry any jurisdiction; a GLEIF-L2 relationship
    is keyed by the global LEI). A new national register is a new provider tagged with
    its market — never a change to the pipeline, which resolves purely by anchor."""

    name: str
    market: str

    def connected(self) -> bool: ...

    def list_ownership(self) -> list[OwnershipRecord]: ...


class StaticOwnershipProvider:
    """Replays a fixed ownership-record list — the hermetic test double, and the
    carrier for records that do not come from BODS (e.g. GLEIF-L2 consolidation)."""

    def __init__(
        self, records: list[OwnershipRecord], *, name: str = "static", market: str = "*"
    ) -> None:
        self.name = name
        self.market = market
        self._records = records

    def connected(self) -> bool:
        return True

    def list_ownership(self) -> list[OwnershipRecord]:
        return list(self._records)


# -- BODS (Beneficial Ownership Data Standard) --------------------------------


def _normalize_scheme(scheme: str) -> str:
    """Fold common identifier scheme names to our anchor vocabulary so a BODS LEI
    resolves against a GLEIF-anchored node, a CIK against an EDGAR node, etc."""

    s = scheme.strip().lower()
    if "lei" in s:
        return "lei"
    if "cik" in s or "edgar" in s:
        return "cik"
    if "isin" in s:
        return "isin"
    return s or "unknown"


def _entity_anchor(identifiers: list[dict[str, Any]]) -> PartyAnchor | None:
    """First usable identifier as a :class:`PartyAnchor`, preferring an LEI (the
    cross-border key). Returns ``None`` when the record carries no identifier."""

    picked: PartyAnchor | None = None
    for ident in identifiers:
        if not isinstance(ident, dict):
            continue
        value = str(ident.get("id") or "").strip()
        if not value:
            continue
        scheme = _normalize_scheme(str(ident.get("scheme") or ident.get("schemeName") or ""))
        anchor = PartyAnchor(scheme=scheme, value=value)
        if scheme == "lei":
            return anchor
        if picked is None:
            picked = anchor
    return picked


def _person_name(statement: dict[str, Any]) -> str:
    names = statement.get("names")
    if isinstance(names, list):
        for n in names:
            if isinstance(n, dict) and n.get("fullName"):
                return str(n["fullName"]).strip()
    return str(statement.get("name") or "Unknown person").strip()


def _share_to_percentage(interest: dict[str, Any]) -> tuple[float | None, str | None]:
    """A BODS ``share`` object → ``(exact_percentage, band)``. Honest: an exact
    figure only when stated; otherwise a disclosed range verbatim; never both, never
    invented."""

    share = interest.get("share")
    if not isinstance(share, dict):
        return None, None
    if isinstance(share.get("exact"), (int, float)):
        return float(share["exact"]), None
    lo = share.get("minimum")
    hi = share.get("maximum")
    lo_n = float(lo) if isinstance(lo, (int, float)) else None
    hi_n = float(hi) if isinstance(hi, (int, float)) else None
    if lo_n is not None and hi_n is not None:
        return None, f"{_fmt(lo_n)}%-{_fmt(hi_n)}%"
    if lo_n is not None:
        return None, f"≥{_fmt(lo_n)}%"
    if hi_n is not None:
        return None, f"≤{_fmt(hi_n)}%"
    return None, None


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def _statements(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        inner = data.get("statements")
        return [s for s in inner if isinstance(s, dict)] if isinstance(inner, list) else []
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []


def parse_bods(text: str) -> list[OwnershipRecord]:
    """Parse a BODS statement array (or ``{"statements": [...]}`` envelope, or the
    newline-delimited variant) into :class:`OwnershipRecord`\\ s.

    Resolves each ownership-or-control statement's ``subject`` and ``interestedParty``
    through the entity/person statements they reference. A person interested party →
    ``beneficial_owner``; an entity → ``declared_shareholding``. Statements that do
    not resolve to both ends are skipped (never a fabricated half-edge)."""

    stripped = text.strip()
    if not stripped:
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # Newline-delimited JSON (the BODS bulk shape): one statement per line.
        rows: list[dict[str, Any]] = []
        for line in stripped.splitlines():
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
        data = rows

    statements = _statements(data)
    entities: dict[str, dict[str, Any]] = {}
    persons: dict[str, dict[str, Any]] = {}
    controls: list[dict[str, Any]] = []
    for st in statements:
        sid = str(st.get("statementID") or st.get("statementId") or "")
        stype = str(st.get("statementType") or "")
        if stype == "entityStatement" and sid:
            entities[sid] = st
        elif stype == "personStatement" and sid:
            persons[sid] = st
        elif stype == "ownershipOrControlStatement":
            controls.append(st)

    records: list[OwnershipRecord] = []
    for st in controls:
        subject_ref = st.get("subject") or {}
        subj_id = str(subject_ref.get("describedByEntityStatement") or "")
        subj = entities.get(subj_id)
        if subj is None:
            continue  # subject must resolve to an entity — no fabricated half-edge
        subject = OwnershipParty(
            name=str(subj.get("name") or "Unknown entity").strip(),
            kind="Company",
            anchor=_entity_anchor(subj.get("identifiers") or []),
        )

        ip = st.get("interestedParty") or {}
        person_id = str(ip.get("describedByPersonStatement") or "")
        entity_id = str(ip.get("describedByEntityStatement") or "")
        if person_id and person_id in persons:
            holder = OwnershipParty(name=_person_name(persons[person_id]), kind="Person")
            basis = OwnershipBasis.BENEFICIAL_OWNER
        elif entity_id and entity_id in entities:
            ent = entities[entity_id]
            holder = OwnershipParty(
                name=str(ent.get("name") or "Unknown entity").strip(),
                kind="Company",
                anchor=_entity_anchor(ent.get("identifiers") or []),
            )
            basis = OwnershipBasis.DECLARED_SHAREHOLDING
        else:
            continue  # interested party must resolve — never a dangling owner

        interests = st.get("interests")
        interests = interests if isinstance(interests, list) else []
        primary = next((i for i in interests if isinstance(i, dict)), {})
        percentage, band = _share_to_percentage(primary)
        interest_type = str(primary.get("type") or "").strip() or None
        start = str(primary.get("startDate") or "").strip() or None
        end = str(primary.get("endDate") or "").strip() or None

        records.append(OwnershipRecord(
            holder=holder, subject=subject, basis=basis,
            percentage=percentage, percentage_band=band, interest=interest_type,
            source=BODS_SOURCE,
            source_url=str(st.get("source", {}).get("url") or "") or None
            if isinstance(st.get("source"), dict) else None,
            valid_from=start, valid_to=end,
        ))
    return records


class BodsOwnershipProvider:
    """Ownership records from a BODS export (OpenOwnership / UK PSC-shaped). File in,
    :class:`OwnershipRecord`\\ s out. Hermetic in CI via injected text; a live
    national-register fetch (UK PSC, etc.) is future work, so ``--file`` is the path."""

    name = "openownership-bods"
    market = "*"  # BODS statements carry their own jurisdiction; market-agnostic

    def __init__(self, *, text: str | None = None) -> None:
        self._text = text

    @classmethod
    def from_file(cls, path: Path) -> "BodsOwnershipProvider":
        return cls(text=Path(path).read_text())

    def connected(self) -> bool:
        return self._text is not None

    def list_ownership(self) -> list[OwnershipRecord]:
        return parse_bods(self._text or "")
