from __future__ import annotations

from collections.abc import Callable
import json
import logging
import time
from datetime import date, datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from coruscant.common.errors import FetchError
from coruscant.common.types import (
    DocumentExhibit,
    DocumentSection,
    EvidenceSpan,
    NormalizedDocument,
    SourceDocument,
    section_id,
)
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import developments_text

logger = logging.getLogger(__name__)


class RateLimiter:
    """Minimum-interval throttle for fair-access compliance (e.g. SEC ~10 req/s).

    A single limiter is shared across every request of a live ingestion run so the
    aggregate request rate stays under the cap. ``monotonic``/``sleep`` are
    injectable so the spacing is deterministically testable without real waiting.
    """

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = max(0.0, min_interval_seconds)
        self._monotonic = monotonic
        self._sleep = sleep
        self._last: float | None = None

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        now = self._monotonic()
        if self._last is not None:
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
        self._last = now


class _TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self.parts)


class StaticEdgarConnector(SourceConnector):
    """Reference connector for SEC filing text already available to the platform."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        raw_text = f"<filing><source>{request.source_uri}</source></filing>"
        return SourceDocument(
            source_type="sec_edgar",
            source_uri=request.source_uri,
            fetched_at=datetime.now(tz=timezone.utc),
            raw_content=raw_text,
            content_type="text/xml",
            source_name=request.source_name,
            metadata={"company_slug": request.company_slug, "source_name": request.source_name},
        )


class ReferenceEdgarConnector(SourceConnector):
    """Synthesizes a deterministic, item-structured filing for offline development.

    Mirrors the shape of a 10-K so :func:`normalize_edgar_filing` exercises real
    form-aware section splitting without requiring network access.
    """

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        form_type = "10-K"
        developments = developments_text(request.revision)
        filing_date = request.published_at or "2025-01-31"
        text = (
            "Item 1. Business\n"
            f"{name} designs, manufactures, and markets products and services across its "
            "core operating segments.\n\n"
            "Item 1A. Risk Factors\n"
            f"{name} faces competitive, supply chain, regulatory, and macroeconomic risks "
            "that could affect results.\n\n"
            "Item 7. Management's Discussion and Analysis\n"
            f"{name} discusses revenue trends, margins, liquidity, and capital allocation "
            f"for the reporting period. {developments}\n"
        )
        return SourceDocument(
            source_type="sec_edgar",
            source_uri=request.source_uri,
            fetched_at=datetime.now(tz=timezone.utc),
            raw_content=text,
            content_type="text/plain",
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "form_type": form_type,
                "title": f"{name} {form_type} ({request.period or filing_date})",
                "filing_date": filing_date,
                "published_at": filing_date,
                "period": request.period,
                "provenance": "reference-sample",
            },
        )


class EdgarHttpConnector(SourceConnector):
    """Fetch SEC filing pages with a plain HTTP client.

    Every outbound request declares the configured ``user_agent`` (SEC requires a
    contact-bearing UA) and passes through the optional shared ``rate_limiter`` so
    a live run respects SEC fair-access limits.
    """

    def __init__(self, user_agent: str, *, rate_limiter: RateLimiter | None = None) -> None:
        self.user_agent = user_agent
        self.rate_limiter = rate_limiter

    def _open(self, url: str):  # type: ignore[no-untyped-def]
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        return urlopen(Request(url, headers={"User-Agent": self.user_agent}), timeout=30)

    def fetch(self, request: FetchRequest) -> SourceDocument:
        # A failure to fetch the primary filing is a hard, explicit error so the
        # orchestrator records it (dead-letter + run report) — never swallowed.
        try:
            with self._open(request.source_uri) as response:
                content_type = response.headers.get("content-type")
                payload = response.read().decode("utf-8", errors="replace")
        except (URLError, OSError) as exc:
            raise FetchError(f"failed to fetch SEC filing {request.source_uri}: {exc}") from exc
        index_data = self._maybe_load_index_json(request.source_uri)
        primary_document_url = index_data.get("primary_document_url")
        primary_document_html = (
            self._fetch_primary_document(str(primary_document_url)) if primary_document_url else None
        )
        filing_text = self._extract_text(primary_document_html or payload)
        metadata_html = index_data.get("metadata_html")
        metadata: dict[str, Any] = self._extract_metadata(
            metadata_html if isinstance(metadata_html, str) else payload
        )
        index_metadata = index_data.get("metadata")
        if isinstance(index_metadata, dict):
            metadata.update(index_metadata)
        if primary_document_url:
            metadata["primary_document_url"] = primary_document_url
        exhibits = index_data.get("exhibits")
        if isinstance(exhibits, list):
            metadata["indexed_exhibits"] = exhibits
        # Exhibit 21 → subsidiaries (best-effort; a fetch/parse miss never fails
        # the 10-K). Provenance travels with the filing's normalized metadata.
        ex21_url = find_exhibit21_url(request.source_uri, metadata.get("indexed_exhibits"))
        if ex21_url:
            ex21_html = self._fetch_primary_document(ex21_url)
            if ex21_html:
                subsidiaries = parse_subsidiaries(self._extract_text(ex21_html))
                if subsidiaries:
                    metadata["subsidiaries"] = subsidiaries
        metadata.update({"company_slug": request.company_slug, "source_name": request.source_name})
        return SourceDocument(
            source_type="sec_edgar",
            source_uri=request.source_uri,
            fetched_at=datetime.now(tz=timezone.utc),
            raw_content=filing_text,
            content_type=content_type,
            source_name=request.source_name,
            metadata=metadata,
        )

    def _extract_text(self, html: str) -> str:
        parser = _TextStripper()
        parser.feed(html)
        text = parser.text().strip()
        return text or html

    def _extract_metadata(self, html: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for label in ("accession number", "filing date", "period of report"):
            value = _extract_label_value(html, label)
            if value:
                metadata[label.replace(" ", "_")] = value
        return metadata

    def _maybe_load_index_json(self, source_uri: str) -> dict[str, object]:
        index_url = filing_index_url(source_uri)
        # The index.json is an optional enrichment; on failure we log (observable)
        # and continue with the primary payload rather than failing the fetch.
        try:
            with self._open(index_url) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except (URLError, OSError) as exc:
            logger.warning("EDGAR index.json unavailable for %s: %s", index_url, exc)
            return {}

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning("EDGAR index.json malformed for %s: %s", index_url, exc)
            return {}

        metadata = _parse_index_metadata(data)
        primary_document_url = _parse_primary_document_url(data, source_uri)
        exhibits = _parse_index_exhibits(data)
        return {
            "metadata": metadata,
            "metadata_html": payload,
            "primary_document_url": primary_document_url,
            "exhibits": exhibits,
        }

    def _fetch_primary_document(self, primary_document_url: str) -> str | None:
        # Best-effort: on failure we log and fall back to the index payload.
        try:
            with self._open(primary_document_url) as response:
                return response.read().decode("utf-8", errors="replace")
        except (URLError, OSError) as exc:
            logger.warning("EDGAR primary document fetch failed for %s: %s", primary_document_url, exc)
            return None


# --- Exhibit 21 (Subsidiaries of the Registrant) ----------------------------
# Deterministic, provenance-backed ownership extraction. Ex-21 is a flat list of
# (subsidiary name, jurisdiction) pairs; we anchor on a known jurisdiction set and
# pair each with the preceding line — robust to header noise, precision-first (an
# unrecognized jurisdiction drops that row rather than inventing an edge).

_US_STATES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|"
    "hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|"
    "michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
    "new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|"
    "rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|"
    "west virginia|wisconsin|wyoming|district of columbia|puerto rico"
)
_COUNTRIES = (
    "united states|usa|canada|mexico|brazil|chile|argentina|colombia|peru|united kingdom|uk|"
    "england|scotland|ireland|france|germany|netherlands|belgium|luxembourg|switzerland|spain|"
    "portugal|italy|austria|sweden|norway|denmark|finland|poland|china|japan|india|singapore|"
    "hong kong|south korea|korea|taiwan|australia|new zealand|south africa|israel|"
    "united arab emirates|uae|cayman islands|bermuda|british virgin islands|jersey|guernsey|"
    "isle of man|mauritius|cyprus|malta|gibraltar|costa rica|panama|guatemala|philippines|"
    "thailand|vietnam|malaysia|indonesia|turkey|russia|ukraine|czech republic|hungary|romania|"
    "greece|egypt|nigeria|kenya|morocco|saudi arabia|qatar|bahrain|kuwait|barbados|bahamas|"
    "curacao|uruguay|ecuador|venezuela|dominican republic|honduras|el salvador|nicaragua|"
    "paraguay|bolivia|slovakia|slovenia|croatia|serbia|bulgaria"
)
_JURISDICTIONS = frozenset(_US_STATES.split("|")) | frozenset(_COUNTRIES.split("|"))
_SUB_HEADERS = {
    "subsidiaries", "name", "document", "exhibit", "organized under", "the laws of",
    "organized under laws of", "registrant", "list of subsidiaries", "subsidiaries of the registrant",
}
_EX21_RE = re.compile(r"exhibit[\s_\-]*21", re.I)


def _norm_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def find_exhibit21_url(source_uri: str, indexed_exhibits: object) -> str | None:
    """Locate the Exhibit 21 (subsidiaries) document URL from a filing's exhibits.

    Matches `exhibit21` / `exhibit 21` / `exhibit21.1` but NOT 32.1, 10.2.1, 23.1
    (the `21` must directly follow `exhibit`, so a leading digit like 3 in `321`
    fails to match).
    """
    if not isinstance(indexed_exhibits, list):
        return None
    for exhibit in indexed_exhibits:
        if not isinstance(exhibit, dict):
            continue
        title = str(exhibit.get("title") or exhibit.get("url") or exhibit.get("href") or "")
        if title and _EX21_RE.search(title):
            return urljoin(source_uri, title)
    return None


def parse_subsidiaries(text: str, *, parent_core: str = "", limit: int = 30) -> list[dict[str, str]]:
    """Parse (name, jurisdiction) subsidiary pairs from Exhibit 21 plain text."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i in range(1, len(lines)):
        if _norm_text(lines[i]) not in _JURISDICTIONS:
            continue
        name = lines[i - 1].strip().rstrip(",;")
        norm = _norm_text(name)
        if len(name) < 3 or len(name) > 90:
            continue
        if norm in _JURISDICTIONS or norm in _SUB_HEADERS:
            continue
        if parent_core and parent_core in norm:  # skip the registrant's self-entry
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"name": name, "jurisdiction": lines[i].strip()})
        if len(out) >= limit:
            break
    return out


def normalize_edgar_filing(document: SourceDocument) -> NormalizedDocument:
    parser = _TextStripper()
    parser.feed(document.raw_content)
    text = parser.text()
    canonical_id = sha256(document.source_uri.encode("utf-8")).hexdigest()
    sections = _split_sections(document, text or document.raw_content, canonical_id)
    exhibits = _extract_exhibits(document)
    indexed_exhibits = document.metadata.get("indexed_exhibits")
    if isinstance(indexed_exhibits, list):
        exhibits.extend(indexed_exhibits)
    metadata = dict(document.metadata)
    if document.source_name:
        metadata.setdefault("source_name", document.source_name)
    return NormalizedDocument(
        document_type="filing",
        source_uri=document.source_uri,
        canonical_id=canonical_id,
        title=document.metadata.get("title")
        or document.metadata.get("company_name")
        or document.metadata.get("form_type"),
        published_at=_parse_date(
            document.metadata.get("filing_date")
            or document.metadata.get("published_at")
            or document.metadata.get("period_of_report")
        ),
        sections=sections,
        exhibits=exhibits,
        entities=_extract_entities(document),
        metadata=metadata,
    )


def _split_sections(document: SourceDocument, text: str, canonical_id: str) -> list[dict[str, object]]:
    form_type = str(document.metadata.get("form_type") or document.source_name or "").upper()
    section_matches = list(_find_section_matches(text, form_type=form_type))
    if not section_matches:
        content = text.strip()
        return [
            DocumentSection(
                title="Raw Filing",
                content=content,
                order=1,
                id=section_id(canonical_id, 1),
                evidence=[_evidence(document.source_uri, "Raw Filing", content)],
            ).model_dump()
        ]

    sections: list[dict[str, object]] = []
    for index, match in enumerate(section_matches):
        start = match.end()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(text)
        content = text[start:end].strip()
        if not content:
            continue
        title = match.group(0).strip()
        order = len(sections) + 1
        sections.append(
            DocumentSection(
                title=title,
                content=content,
                order=order,
                id=section_id(canonical_id, order),
                anchor=_slugify(title),
                evidence=[
                    _evidence(document.source_uri, title, content),
                    _evidence(document.source_uri, "filing-form", form_type or "unknown"),
                ],
            ).model_dump()
        )
    if not sections:
        content = text.strip()
        sections.append(
            DocumentSection(
                title="Raw Filing",
                content=content,
                order=1,
                id=section_id(canonical_id, 1),
                anchor="raw-filing",
                evidence=[_evidence(document.source_uri, "Raw Filing", content)],
            ).model_dump()
        )
    return sections


def _extract_exhibits(document: SourceDocument) -> list[dict[str, object]]:
    if "exhibit" not in document.raw_content.lower():
        return []
    return [
        DocumentExhibit(
            title="Exhibit Reference",
            content="Exhibit referenced in filing",
            exhibit_number=_extract_exhibit_number(document.raw_content),
            url=document.metadata.get("primary_document_url"),
            evidence=[_evidence(document.source_uri, "Exhibit Reference", "Exhibit referenced in filing")],
        ).model_dump()
    ]


def _extract_entities(document: SourceDocument) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    company_slug = document.metadata.get("company_slug")
    if company_slug:
        entities.append(
            {
                "kind": "Company",
                "key": company_slug,
                "name": document.metadata.get("company_name", company_slug),
            }
        )
    accession_number = document.metadata.get("accession_number")
    if accession_number:
        entities.append(
            {
                "kind": "Filing",
                "key": accession_number,
                "name": document.metadata.get("title", accession_number),
            }
        )
    return entities


def _looks_like_section_heading(line: str) -> bool:
    normalized = line.strip().lower()
    return bool(_item_heading_pattern().match(normalized)) or normalized.startswith("part ")


def _extract_exhibit_number(text: str) -> str | None:
    lowered = text.lower()
    for marker in ("exhibit 21", "exhibit 23", "exhibit 31", "exhibit 32"):
        if marker in lowered:
            return marker.split()[1]
    return None


def _evidence(source_uri: str, section_title: str, excerpt: str) -> EvidenceSpan:
    return EvidenceSpan(
        source_uri=source_uri,
        section_title=section_title,
        excerpt=excerpt[:280],
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _find_section_matches(text: str, form_type: str = "") -> list[re.Match[str]]:
    pattern = _template_pattern_for_form(form_type)
    matches = list(pattern.finditer(text.lower()))
    if matches:
        return matches
    return list(_item_heading_pattern().finditer(text.lower()))


def _item_heading_pattern() -> re.Pattern[str]:
    return re.compile(r"(?m)^(item\s+[0-9a-zivx]+\.[^\n]*)")


def _template_pattern_for_form(form_type: str) -> re.Pattern[str]:
    templates: dict[str, str] = {
        "10-K": r"(?m)^(item\s+(?:1a|1b|1c|1|2|3|4|5|6|7|7a|8|9|9a|9b|9c|10|11|12|13|14|15)\.[^\n]*)",
        "10-Q": r"(?m)^(item\s+(?:1|1a|2|3|4)\.[^\n]*)",
        "8-K": r"(?m)^(item\s+(?:1\.01|1\.02|2\.01|2\.02|3\.01|5\.01|5\.02|5\.03|8\.01|9\.01)\.[^\n]*)",
        "DEF 14A": r"(?m)^(item\s+(?:1|2|3|4|5|6|7)\.[^\n]*)",
    }
    pattern = templates.get(form_type.upper())
    if pattern:
        return re.compile(pattern)
    return _item_heading_pattern()


def _parse_date(value: object) -> datetime | date | None:
    if isinstance(value, (datetime, date)):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _parse_index_metadata(data: dict[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    filing = data.get("filing")
    if isinstance(filing, dict):
        accession = filing.get("accessionNumber") or filing.get("accession_number")
        if accession:
            metadata["accession_number"] = accession
        filing_date = filing.get("filingDate") or filing.get("filing_date")
        if filing_date:
            metadata["filing_date"] = filing_date
        report_date = filing.get("periodOfReport") or filing.get("period_of_report")
        if report_date:
            metadata["period_of_report"] = report_date
        company = filing.get("companyName") or filing.get("company_name")
        if company:
            metadata["company_name"] = company
    return metadata


def _parse_primary_document_url(data: dict[str, object], source_uri: str) -> str | None:
    directory = data.get("directory")
    if not isinstance(directory, dict):
        return None
    items = directory.get("item")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "10-K" or item.get("name") == "primary document":
            link = item.get("href") or item.get("name")
            if isinstance(link, str):
                return urljoin(source_uri, link)
    return None


def _parse_index_exhibits(data: dict[str, object]) -> list[dict[str, object]]:
    directory = data.get("directory")
    if not isinstance(directory, dict):
        return []
    items = directory.get("item")
    if not isinstance(items, list):
        return []
    exhibits: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if "exhibit" not in name.lower():
            continue
        exhibits.append(
            DocumentExhibit(
                title=name,
                content=str(item.get("href") or ""),
                exhibit_number=_extract_exhibit_number(name),
                url=str(item.get("href") or ""),
                evidence=[],
            ).model_dump()
        )
    return exhibits


def _extract_label_value(html: str, label: str) -> str | None:
    lowered = html.lower()
    start = lowered.find(label.lower())
    if start == -1:
        return None
    snippet = html[start : start + 300]
    if "</td>" in snippet:
        snippet = snippet.split("</td>", 1)[0]
    if ">" in snippet:
        snippet = snippet.rsplit(">", 1)[-1]
    return unescape(snippet).strip(" :\n\t\r") or None


def filing_index_url(filing_url: str) -> str:
    return urljoin(filing_url, "index.json")
