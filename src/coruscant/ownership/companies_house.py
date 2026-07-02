"""UK Companies House PSC — the first *live* national beneficial-ownership source.

The UK Persons-with-Significant-Control register is a free, **public** register:
unlike EU member-state registers (locked down post-CJEU C-37/20, restored only for
legitimate-interest access under AMLR), the UK PSC register remained fully public
after Brexit. So PSC beneficial-owner edges are stamped :class:`AccessTier.PUBLIC`
via the record's ``access_tier`` override — a documented, per-source decision the
substrate was designed to carry, distinct from the BODS/EU default (legitimate-
interest). The one exception is a *super-secure* PSC, whose identity is legally
protected: its details are withheld and it is stamped ``RESTRICTED_AUTHORITY``, an
explicitly-labelled restricted item (never a fabricated name).

Two shapes parse identically (:func:`parse_psc`), honesty-preserving throughout:

* the **Public Data API** ``/company/{n}/persons-with-significant-control`` response
  (``{"items": [...], "links": {"self": ".../company/09999999/..."}}``), and
* the **bulk PSC snapshot** newline-delimited JSON (one ``{"company_number", "data"}``
  row per line — the operator-download fallback for the whole register).

The PSC ``kind`` selects the :class:`OwnershipBasis` exactly as BODS does — an
*individual* PSC is a ``beneficial_owner`` (a natural person's control), a *corporate*
or *legal-person* PSC a ``declared_shareholding`` (an entity interest) — so the three
distinct edge types are never conflated. ``natures_of_control`` carry disclosed
percentage *bands* (``ownership-of-shares-25-to-50-percent``); we record the band
verbatim and never invent an exact figure. A PSC *statement* (``psc-exists-but-not-
identified`` etc.) is not an ownership edge — it is counted, never emitted as one.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from coruscant.knowledge_graph import substrate
from coruscant.ownership.models import (
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
)

COMPANIES_HOUSE_PSC_SOURCE = "uk-companies-house-psc"
_CH_API = "https://api.company-information.service.gov.uk"

# PSC `kind` → (party kind, ownership basis). An individual is a natural person's
# ultimate control (beneficial owner); a corporate/legal-person PSC is an entity
# interest (a declared shareholding), mirroring the BODS person/entity split.
_INDIVIDUAL = "individual-person-with-significant-control"
_CORPORATE = "corporate-entity-person-with-significant-control"
_LEGAL_PERSON = "legal-person-person-with-significant-control"
_SUPER_SECURE = "super-secure-person-with-significant-control"
_STATEMENT = "persons-with-significant-control-statement"

# Nature-of-control band tokens → (interest label, disclosed percentage band). The
# `-as-firm`/`-as-trust` variants (the PSC holds via a firm/trust) carry the same
# band, so they are folded to the base token before lookup.
_OWNERSHIP_BANDS = {
    "ownership-of-shares-25-to-50-percent": "25%-50%",
    "ownership-of-shares-50-to-75-percent": "50%-75%",
    "ownership-of-shares-75-to-100-percent": "75%-100%",
}
_VOTING_BANDS = {
    "voting-rights-25-to-50-percent": "25%-50%",
    "voting-rights-50-to-75-percent": "50%-75%",
    "voting-rights-75-to-100-percent": "75%-100%",
}


def _fold_nature(token: str) -> str:
    """Strip the ``-as-firm`` / ``-as-trust`` holding-vehicle suffix so a nature of
    control resolves to its base band regardless of how the PSC holds the interest."""

    for suffix in ("-as-firm", "-as-trust", "-as-control-over-trust", "-as-control-over-firm"):
        if token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _interpret_natures(natures: list[str]) -> tuple[str | None, str | None]:
    """A PSC ``natures_of_control`` list → ``(interest, percentage_band)``. Honest:
    the band is only ever a *disclosed range* (PSC discloses bands, never exact
    figures), and the widest disclosed band wins when several are present. The
    interest names the nature of control so a beneficial-owner edge is unambiguous."""

    band: str | None = None
    interest: str | None = None
    order = ["25%-50%", "50%-75%", "75%-100%"]
    for raw in natures:
        token = _fold_nature(str(raw).strip().lower())
        if token in _OWNERSHIP_BANDS:
            interest = interest or "shareholding"
            candidate = _OWNERSHIP_BANDS[token]
        elif token in _VOTING_BANDS:
            interest = interest or "voting-rights"
            candidate = _VOTING_BANDS[token]
        elif "right-to-appoint-and-remove" in token:
            interest = interest or "appoint-directors"
            continue
        elif "significant-influence-or-control" in token:
            interest = interest or "significant-influence"
            continue
        else:
            continue
        if band is None or (candidate in order and order.index(candidate) > order.index(band)):
            band = candidate
    return interest, band


def _person_name(data: dict[str, Any]) -> str:
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    elements = data.get("name_elements")
    if isinstance(elements, dict):
        parts = [
            str(elements.get(k) or "").strip()
            for k in ("forename", "middle_name", "surname")
        ]
        joined = " ".join(p for p in parts if p)
        if joined:
            return joined
    return "Unknown person"


def _entity_anchor(data: dict[str, Any]) -> PartyAnchor | None:
    """Anchor a corporate/legal-person PSC by its registration number where the
    registry is UK Companies House, so it resolves against an LSE-covered node's
    ``company_number`` anchor (enrich, don't duplicate). Other registries keep their
    own scheme so a later ER pass can merge them — never fabricated."""

    ident = data.get("identification")
    if not isinstance(ident, dict):
        return None
    number = str(ident.get("registration_number") or "").strip()
    if not number:
        return None
    registry = " ".join(str(ident.get("place_registered") or "").split()).lower()
    country = str(ident.get("country_registered") or "").strip().lower()
    if "companies house" in registry or country in ("united kingdom", "england", "uk", "gb", "england/wales"):
        return PartyAnchor(scheme="company_number", value=number)
    scheme = "registration_number"
    return PartyAnchor(scheme=scheme, value=number)


def _subject(company_number: str, company_name: str | None) -> OwnershipParty:
    return OwnershipParty(
        name=(company_name or f"UK company {company_number}").strip() or f"UK company {company_number}",
        kind="Company",
        anchor=PartyAnchor(scheme="company_number", value=company_number) if company_number else None,
    )


def _record_from_psc(
    data: dict[str, Any], subject: OwnershipParty, *, company_number: str
) -> OwnershipRecord | None:
    """One PSC ``data`` object → an :class:`OwnershipRecord`, or ``None`` when it is
    a statement (not an ownership edge). Super-secure PSCs are emitted but withheld:
    a restricted-tier beneficial-owner edge with the identity explicitly labelled."""

    kind = str(data.get("kind") or "").strip().lower()
    if not kind or kind == _STATEMENT:
        return None  # a PSC statement is counted by the caller, never a half-edge

    notified_on = str(data.get("notified_on") or "").strip() or None
    ceased_on = str(data.get("ceased_on") or "").strip() or None
    natures = data.get("natures_of_control")
    interest, band = _interpret_natures(natures if isinstance(natures, list) else [])
    source_url = (
        f"https://find-and-update.company-information.service.gov.uk/company/{company_number}/persons-with-significant-control"
        if company_number
        else None
    )

    if kind == _SUPER_SECURE:
        # Identity legally protected — labelled, not fabricated, and access-restricted.
        return OwnershipRecord(
            holder=OwnershipParty(name="Super-secure person (details withheld)", kind="Person"),
            subject=subject, basis=OwnershipBasis.BENEFICIAL_OWNER,
            percentage_band=band, interest=interest or "significant-influence",
            source=COMPANIES_HOUSE_PSC_SOURCE, source_url=source_url,
            valid_from=notified_on, valid_to=ceased_on,
            access_tier=substrate.AccessTier.RESTRICTED_AUTHORITY.value,
        )
    if kind == _INDIVIDUAL:
        return OwnershipRecord(
            holder=OwnershipParty(name=_person_name(data), kind="Person"),
            subject=subject, basis=OwnershipBasis.BENEFICIAL_OWNER,
            percentage_band=band, interest=interest,
            source=COMPANIES_HOUSE_PSC_SOURCE, source_url=source_url,
            valid_from=notified_on, valid_to=ceased_on,
            # UK PSC is a PUBLIC register (unlike EU registers post-CJEU C-37/20).
            access_tier=substrate.AccessTier.PUBLIC.value,
        )
    if kind in (_CORPORATE, _LEGAL_PERSON):
        holder = OwnershipParty(
            name=_person_name(data), kind="Company" if kind == _CORPORATE else "Entity",
            anchor=_entity_anchor(data),
        )
        return OwnershipRecord(
            holder=holder, subject=subject, basis=OwnershipBasis.DECLARED_SHAREHOLDING,
            percentage_band=band, interest=interest,
            source=COMPANIES_HOUSE_PSC_SOURCE, source_url=source_url,
            valid_from=notified_on, valid_to=ceased_on,
        )
    return None  # an unknown kind is skipped, never guessed at


def _self_company_number(payload: dict[str, Any]) -> str:
    """The subject company number for an API response, read from ``links.self``
    (``/company/09999999/persons-with-significant-control``)."""

    links = payload.get("links")
    if isinstance(links, dict):
        self_link = str(links.get("self") or "")
        parts = [p for p in self_link.split("/") if p]
        if "company" in parts:
            i = parts.index("company")
            if i + 1 < len(parts):
                return parts[i + 1]
    return ""


class PscParseStats:
    """What a PSC parse produced and, honestly, what it did not turn into an edge."""

    __slots__ = ("records", "statements", "skipped")

    def __init__(self) -> None:
        self.records: list[OwnershipRecord] = []
        self.statements = 0  # PSC statements (no-PSC / not-identified) — not edges
        self.skipped = 0  # unknown/unparseable PSC kinds


def _parse_api_items(payload: dict[str, Any], stats: PscParseStats, *, company_number: str = "") -> None:
    number = company_number or _self_company_number(payload)
    subject = _subject(number, None)
    items = payload.get("items")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            stats.skipped += 1
            continue
        _accumulate(item, subject, number, stats)


def _parse_bulk_row(row: dict[str, Any], stats: PscParseStats) -> None:
    number = str(row.get("company_number") or "").strip()
    company_name = row.get("company_name")
    subject = _subject(number, company_name if isinstance(company_name, str) else None)
    data = row.get("data")
    if isinstance(data, dict):
        _accumulate(data, subject, number, stats)
    else:
        stats.skipped += 1


def _accumulate(data: dict[str, Any], subject: OwnershipParty, number: str, stats: PscParseStats) -> None:
    kind = str(data.get("kind") or "").strip().lower()
    if kind == _STATEMENT:
        stats.statements += 1
        return
    record = _record_from_psc(data, subject, company_number=number)
    if record is not None:
        stats.records.append(record)
    else:
        stats.skipped += 1


def parse_psc(text: str) -> PscParseStats:
    """Parse PSC JSON — an API response, a list of API responses, a single ``data``
    object, or the bulk NDJSON snapshot — into a :class:`PscParseStats`. Robust to
    the mix Companies House ships; unparseable lines are counted, never crash."""

    stats = PscParseStats()
    stripped = text.strip()
    if not stripped:
        return stats
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                stats.skipped += 1
                continue
            _dispatch(obj, stats)
        return stats
    _dispatch(data, stats)
    return stats


def _dispatch(obj: Any, stats: PscParseStats) -> None:
    if isinstance(obj, list):
        for item in obj:
            _dispatch(item, stats)
        return
    if not isinstance(obj, dict):
        stats.skipped += 1
        return
    if "items" in obj:  # an API persons-with-significant-control response
        _parse_api_items(obj, stats)
    elif "company_number" in obj and "data" in obj:  # a bulk snapshot row
        _parse_bulk_row(obj, stats)
    elif "kind" in obj:  # a bare PSC data object
        _accumulate(obj, _subject("", None), "", stats)
    else:
        stats.skipped += 1


class CompaniesHousePscProvider:
    """UK PSC ownership records, live from the Companies House Public Data API or
    from a downloaded bulk PSC snapshot.

    Live path (primary): construct with ``api_key`` + the ``company_numbers`` to
    fetch (typically the UK-covered universe), and each company's PSC list is pulled
    from ``/company/{n}/persons-with-significant-control``. Operator fallback:
    ``from_file`` parses a bulk snapshot (NDJSON) for the whole register offline.
    Hermetic in CI via injected ``text``/``payloads`` — no network reaches tests."""

    name = COMPANIES_HOUSE_PSC_SOURCE
    market = "GB"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        company_numbers: list[str] | None = None,
        base_url: str = _CH_API,
        text: str | None = None,
        payloads: list[dict[str, Any]] | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._company_numbers = [str(n).strip() for n in (company_numbers or []) if str(n).strip()]
        self._base_url = base_url.rstrip("/")
        self._text = text
        self._payloads = payloads  # offline injection (tests / already-fetched responses)
        self._timeout = timeout
        self._last_stats = PscParseStats()

    @classmethod
    def from_file(cls, path: Path, **kwargs: Any) -> "CompaniesHousePscProvider":
        """Build a provider that reads a downloaded bulk PSC snapshot — the operator
        fallback for the whole register, no API key required."""

        return cls(text=Path(path).read_text(), **kwargs)

    def connected(self) -> bool:
        return self._text is not None or self._payloads is not None or bool(self._api_key)

    @property
    def last_stats(self) -> PscParseStats:
        return self._last_stats

    def _auth_header(self) -> dict[str, str]:
        # Companies House uses HTTP Basic with the API key as the username and an
        # empty password.
        token = base64.b64encode(f"{self._api_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def _fetch_company(self, number: str) -> dict[str, Any]:
        url = f"{self._base_url}/company/{number}/persons-with-significant-control"
        req = Request(url, headers=self._auth_header())
        try:
            with urlopen(req, timeout=self._timeout) as response:  # noqa: S310 (trusted CH host)
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                return {"items": [], "links": {"self": f"/company/{number}/persons-with-significant-control"}}
            raise RuntimeError(f"Companies House PSC fetch failed for {number}: {error}") from error
        except Exception as error:  # noqa: BLE001 — surface as an explicit runtime failure
            raise RuntimeError(f"Companies House PSC fetch failed for {number}: {error}") from error
        return payload if isinstance(payload, dict) else {}

    def list_ownership(self) -> list[OwnershipRecord]:
        stats = PscParseStats()
        if self._payloads is not None:
            for payload in self._payloads:
                _dispatch(payload, stats)
        elif self._text is not None:
            stats = parse_psc(self._text)
        elif self._api_key and self._company_numbers:
            for number in self._company_numbers:
                _parse_api_items(self._fetch_company(number), stats, company_number=number)
        self._last_stats = stats
        return list(stats.records)
