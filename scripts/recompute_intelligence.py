"""Re-derive the intelligence store (change-sets, events, summaries) from the
normalized documents already on disk — offline, no re-fetch.

Use it after changing the change-detection / event / summary logic (e.g. the
``is_disclosure_sentence`` denoise gate) so the precomputed SqliteIntelligenceStore
reflects the new logic without a full re-ingest:

    CORUSCANT_DATABASE_URL=sqlite:///$PWD/data/coruscant.db \\
      CORUSCANT_DATA_DIR=data python3 scripts/recompute_intelligence.py

Documents are paired newest-vs-prior by the filing date in their EDGAR URL
(`…/v-20250930.htm`), because these normalized docs carry no `published_at`. The
change_sets table is cleared first so a re-run can't leave a stale or
reverse-direction duplicate (events/summaries are keyed per document and simply
replaced in place).
"""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from coruscant.apps.runtime import build_intelligence_store
from coruscant.common.config import Settings
from coruscant.intelligence.changes import ReferenceChangeDetector
from coruscant.intelligence.events import ReferenceEventExtractor
from coruscant.intelligence.summarizer import ReferenceSummarizer
from coruscant.knowledge_graph.extraction import load_normalized_documents

_SOURCE_TYPE = "sec_edgar"


def _filing_date(source_uri: str | None) -> str:
    match = re.search(r"(\d{8})\.html?$", source_uri or "")
    return match.group(1) if match else ""


def main() -> None:
    settings = Settings()
    store = build_intelligence_store(settings)
    with Session(store.engine) as session:
        session.execute(text("DELETE FROM change_sets"))
        session.commit()

    documents = load_normalized_documents(settings.data_dir)
    by_company: dict[str, list] = defaultdict(list)
    for document in documents:
        slug = document.metadata.get("company_slug")
        if slug:
            by_company[str(slug)].append(document)

    detector = ReferenceChangeDetector()
    extractor = ReferenceEventExtractor()
    summarizer = ReferenceSummarizer()
    change_sets = events = 0

    for slug, docs in by_company.items():
        docs.sort(key=lambda d: _filing_date(d.source_uri))  # ascending → [-1] newest
        for document in docs:
            store.save_summary(summarizer.summarize(document, company_slug=slug, source_type=_SOURCE_TYPE))
            extracted = extractor.extract(document, company_slug=slug, source_type=_SOURCE_TYPE)
            store.replace_events(document.canonical_id, extracted)
            events += len(extracted)
        if len(docs) >= 2:
            store.save_change_set(
                detector.diff(docs[-1], docs[-2], company_slug=slug, source_type=_SOURCE_TYPE)
            )
            change_sets += 1

    print(f"Re-derived {change_sets} change-sets and {events} events over {len(documents)} documents.")


if __name__ == "__main__":
    main()
