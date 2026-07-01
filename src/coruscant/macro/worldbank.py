"""Free country indicators from the World Bank API (no key).

One indicator per call against ``/v2/country/{code}/indicator/{id}?mrv=1`` (most
recent value). The API is slow and occasionally times out from some networks, so
callers bound the timeout and cache aggressively (the values change ~yearly). A
failed or empty fetch yields ``None`` — the tile shows "—", never a made-up
figure (the platform's first rule)."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel

_URL = "https://api.worldbank.org/v2/country/{code}/indicator/{indicator}?format=json&mrv=1"
_USER_AGENT = "Coruscant/0.1 (+contact@coruscant.local)"


class Indicator(BaseModel):
    code: str
    value: float
    year: str


def parse_indicator(indicator: str, payload: Any) -> Indicator | None:
    """Build an :class:`Indicator` from a World Bank response, or ``None`` if the
    most-recent value is missing."""
    try:
        rows = payload[1]
    except (IndexError, KeyError, TypeError):
        return None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("value"), (int, float)):
            return Indicator(code=indicator, value=float(row["value"]), year=str(row.get("date") or ""))
    return None


def fetch_indicator(country_code: str, indicator: str, *, timeout: float = 8.0) -> Indicator | None:
    url = _URL.format(code=country_code, indicator=indicator)
    try:
        with urlopen(Request(url, headers={"User-Agent": _USER_AGENT}), timeout=timeout) as resp:
            payload = json.load(resp)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None
    return parse_indicator(indicator, payload)
