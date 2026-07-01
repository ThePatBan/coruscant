"""Free business-news headlines from GDELT's DOC 2.0 API (no key).

One HTTP call returns a JSON ``artlist`` of recent articles matching a query.
GDELT is aggressively rate-limited (HTTP 429), so the calling service gates our
request rate and caches; here we only fetch + parse. A failed or malformed
response yields an empty list — the rail shows "no headlines", never fabricated
ones (the platform's first rule)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel

_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_USER_AGENT = "Mozilla/5.0 (compatible; Coruscant/0.1; +contact@coruscant.local)"


class Article(BaseModel):
    title: str
    url: str
    domain: str | None = None
    published_at: str | None = None  # ISO-8601
    source_country: str | None = None
    language: str | None = None
    image: str | None = None


def _parse_seendate(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def parse_articles(payload: Any, *, limit: int) -> list[Article]:
    """Build de-duplicated :class:`Article` records from a GDELT artlist payload."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("articles")
    if not isinstance(raw, list):
        return []
    articles: list[Article] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        title = item.get("title")
        if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
            continue
        if url in seen:
            continue
        seen.add(url)
        articles.append(
            Article(
                title=title.strip(),
                url=url,
                domain=item.get("domain") if isinstance(item.get("domain"), str) else None,
                published_at=_parse_seendate(item.get("seendate")),
                source_country=item.get("sourcecountry") if isinstance(item.get("sourcecountry"), str) else None,
                language=item.get("language") if isinstance(item.get("language"), str) else None,
                image=item.get("socialimage") if isinstance(item.get("socialimage"), str) and item.get("socialimage") else None,
            )
        )
        if len(articles) >= limit:
            break
    return articles


def fetch_articles(query: str, *, max_records: int = 15, timeout: float = 12.0) -> list[Article]:
    params = urlencode(
        {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "sort": "datedesc",
            "timespan": "3d",
        }
    )
    url = f"{_URL}?{params}"
    try:
        with urlopen(Request(url, headers={"User-Agent": _USER_AGENT}), timeout=timeout) as resp:
            payload = json.load(resp)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return []
    return parse_articles(payload, limit=max_records)
