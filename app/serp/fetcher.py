"""Web content fetching via Firecrawl API."""

import asyncio
import logging
from functools import lru_cache

from firecrawl import FirecrawlApp

from app.config import settings

log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30


@lru_cache(maxsize=1)
def _get_app() -> FirecrawlApp:
    return FirecrawlApp(api_key=settings.firecrawl_api_key)


async def fetch_page_content(url: str, max_chars: int = 10000) -> tuple[str, int]:
    """Fetch a URL's content as markdown via Firecrawl."""
    app = _get_app()
    result = await asyncio.wait_for(
        asyncio.to_thread(app.scrape, url, formats=["markdown"]),
        timeout=_FETCH_TIMEOUT,
    )
    md = result.markdown or ""
    truncated = md[:max_chars]
    word_count = len(truncated.split())
    return truncated, word_count


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Search the web via Firecrawl and return results."""
    app = _get_app()
    results = await asyncio.wait_for(
        asyncio.to_thread(app.search, query, limit=num_results),
        timeout=_FETCH_TIMEOUT,
    )
    items = getattr(results, "web", None) or []
    return [
        {
            "url": r.url or "",
            "title": r.title or "",
            "description": r.description or "",
        }
        for r in items
    ]
