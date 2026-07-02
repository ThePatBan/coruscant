"""Business-news headlines for the World tab, from GDELT's free DOC 2.0 API (no
key). GDELT rate-limits hard, so the service gates our request rate and caches
aggressively; a failed fetch yields no articles (with a note), never invented
headlines.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7."""

from coruscant.news.gdelt import Article, fetch_articles, parse_articles
from coruscant.news.service import NewsFeed, NewsService

__all__ = ["Article", "NewsFeed", "NewsService", "fetch_articles", "parse_articles"]
