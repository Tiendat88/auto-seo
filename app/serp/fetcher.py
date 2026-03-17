"""Web content fetching via Firecrawl API."""

import logging

from app.config import settings

log = logging.getLogger(__name__)


async def fetch_page_content(url: str, max_chars: int = 10000) -> tuple[str, int]:
    """Fetch a URL's content as markdown via Firecrawl."""
    from firecrawl import FirecrawlApp

    app = FirecrawlApp(api_key=settings.firecrawl_api_key)
    result = app.scrape(url, formats=["markdown"])
    md = result.markdown or ""
    word_count = len(md.split())
    return md[:max_chars], word_count


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Search the web via Firecrawl and return results."""
    from firecrawl import FirecrawlApp

    app = FirecrawlApp(api_key=settings.firecrawl_api_key)
    results = app.search(query, limit=num_results)
    items = results.web or [] if hasattr(results, "web") else []
    return [
        {
            "url": r.url or "",
            "title": r.title or "",
            "description": r.description or "",
        }
        for r in items
    ]
