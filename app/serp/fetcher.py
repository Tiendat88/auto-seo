"""Web content fetching via Firecrawl API."""

import asyncio
import logging

from firecrawl import FirecrawlApp

from app.config import settings

log = logging.getLogger(__name__)

_app: FirecrawlApp | None = None


def _get_app() -> FirecrawlApp:
    global _app
    if _app is None:
        _app = FirecrawlApp(api_key=settings.firecrawl_api_key)
    return _app


async def fetch_page_content(url: str, max_chars: int = 10000) -> tuple[str, int]:
    """Fetch a URL's content as markdown via Firecrawl."""
    app = _get_app()
    result = await asyncio.to_thread(app.scrape, url, formats=["markdown"])
    md = result.markdown or ""
    word_count = len(md.split())
    return md[:max_chars], word_count


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Search the web via Firecrawl and return results."""
    app = _get_app()
    results = await asyncio.to_thread(app.search, query, limit=num_results)
    items = getattr(results, "web", None) or []
    return [
        {
            "url": r.url or "",
            "title": r.title or "",
            "description": r.description or "",
        }
        for r in items
    ]
