"""Deterministic, auditable text matching for entity resolution.

Shared by PEP/sanctions screening (person names) and GLEIF LEI anchoring (org
names). Two scorers because the failure modes differ:

* :func:`name_score` — person names: a conservative token/character blend. Only
  exact or reversed-order names clear a useful bar (precision-first; recall is
  yente's job).
* :func:`org_score` — organisation names: our node names are common labels
  ("Apple", "3M") while registries hold legal names ("Apple Inc.", "3M COMPANY").
  So it compares **cores** with corporate suffixes stripped — "apple" == core of
  "apple inc" → strong — while still rejecting "apple ford inc" (core "apple ford").

Romanization is a recall aid only; the native-script original stays canonical on
the node (Invariant #3).
"""

from __future__ import annotations

import difflib
import re
import unicodedata


def normalize_name(name: str) -> str:
    """Fold to a comparable form: strip diacritics (NFKD), casefold, keep only
    alphanumeric tokens, collapse whitespace."""

    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", stripped.casefold()))


def tokens(normalized: str) -> set[str]:
    return set(normalized.split())


def name_score(a: str, b: str) -> float:
    """Conservative similarity of two normalized *person* names in [0, 1]."""

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = tokens(a), tokens(b)
    if ta == tb:  # same tokens, different order ("john smith" vs "smith john")
        return 0.98
    union = ta | tb
    jaccard = len(ta & tb) / len(union) if union else 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return round(0.5 * jaccard + 0.5 * ratio, 4)


# Corporate designators dropped when comparing organisation-name cores.
_ORG_SUFFIXES: frozenset[str] = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "llc", "lp", "llp", "ltd", "limited", "plc", "sa", "ag", "nv", "bv", "gmbh",
    "ulc", "pjsc", "sarl", "spa", "srl", "oyj", "ab", "as", "kk", "pte",
    "holdings", "holding", "group", "the",
})


def org_core(normalized: str) -> str:
    """The organisation name with corporate designators removed (e.g. "apple inc"
    → "apple"), so legal-name variants of the same entity share a core."""

    return " ".join(t for t in normalized.split() if t not in _ORG_SUFFIXES)


def org_score(a: str, b: str) -> float:
    """Similarity of two normalized *organisation* names in [0, 1], suffix-aware."""

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    core_a, core_b = org_core(a), org_core(b)
    if core_a and core_a == core_b:  # same core, different corporate suffixes
        return 0.97
    ta, tb = tokens(a), tokens(b)
    if ta and ta <= tb:  # every query token appears in the candidate (weaker)
        return 0.90
    return name_score(a, b)


# US states / territories collapse to the country "US"; a small map covers the
# jurisdictions our Exhibit-21 subsidiaries actually carry. Unknown → None (then
# jurisdiction can't corroborate a match, so it routes to review).
_US_SUBDIVISIONS: frozenset[str] = frozenset({
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho", "illinois",
    "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
    "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah",
    "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "puerto rico",
})

_JURISDICTION_COUNTRY: dict[str, str] = {
    "united states": "US", "usa": "US", "u s a": "US",
    "united kingdom": "GB", "england and wales": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "great britain": "GB", "uk": "GB",
    "canada": "CA", "netherlands": "NL", "the netherlands": "NL",
    "germany": "DE", "france": "FR", "china": "CN", "hong kong": "HK",
    "japan": "JP", "india": "IN", "ireland": "IE", "switzerland": "CH",
    "luxembourg": "LU", "singapore": "SG", "australia": "AU", "brazil": "BR",
    "italy": "IT", "spain": "ES", "sweden": "SE", "belgium": "BE",
    "mexico": "MX", "bermuda": "BM", "cayman islands": "KY",
}


def jurisdiction_country(jurisdiction: str) -> str | None:
    """Map an Exhibit-21 jurisdiction ("Delaware", "England and Wales") to an ISO
    3166-1 alpha-2 country code, to corroborate a GLEIF match. Unknown → None."""

    key = jurisdiction.replace("\xa0", " ").strip().lower()
    if not key:
        return None
    if key in _US_SUBDIVISIONS:
        return "US"
    return _JURISDICTION_COUNTRY.get(key)
