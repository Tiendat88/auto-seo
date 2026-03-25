"""Web content fetching via the Firecrawl Python SDK."""

import asyncio
import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from firecrawl import Firecrawl

from app.config import settings

log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30
_FETCH_SEMAPHORE: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _FETCH_SEMAPHORE
    if _FETCH_SEMAPHORE is None:
        _FETCH_SEMAPHORE = asyncio.Semaphore(2)  # type: ignore[reportConstantRedefinition]
    return _FETCH_SEMAPHORE


@lru_cache(maxsize=1)
def _get_app() -> Firecrawl:
    return Firecrawl(api_key=settings.firecrawl_api_key)


async def _firecrawl_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a Firecrawl SDK call in a thread with concurrency limiting."""
    async with _get_semaphore():
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=_FETCH_TIMEOUT,
        )


async def fetch_page_content(url: str, max_chars: int = 10000) -> tuple[str, int]:
    """Fetch a URL's content as markdown via Firecrawl."""
    app = _get_app()
    result = await _firecrawl_call(
        app.scrape, url, formats=["markdown"], only_main_content=True,
    )
    md = result.markdown or ""
    truncated = md[:max_chars]
    word_count = len(truncated.split())
    return truncated, word_count


async def fetch_page_full(url: str, max_chars: int = 50000) -> dict:
    """Fetch a URL as both HTML and markdown via Firecrawl.

    Returns dict with keys: html, markdown, metadata.
    HTML for structural checks (headings, paragraphs),
    markdown for clean text (readability, gap analysis).
    only_main_content strips nav/footer/boilerplate on the Firecrawl side.
    """
    app = _get_app()
    result = await _firecrawl_call(
        app.scrape, url,
        formats=["markdown", "html"], only_main_content=True,
    )
    metadata = {}
    if hasattr(result, "metadata") and result.metadata:
        m = result.metadata
        metadata = {
            "title": getattr(m, "title", None) or "",
            "description": getattr(m, "description", None) or "",
            "language": getattr(m, "language", None) or "",
            "status_code": getattr(m, "statusCode", None) or 200,
        }
    return {
        "html": (result.html or "")[:max_chars],
        "markdown": (result.markdown or "")[:max_chars],
        "metadata": metadata,
    }


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Search the web via Firecrawl and return results."""
    app = _get_app()
    results = await _firecrawl_call(app.search, query, limit=num_results)
    items = getattr(results, "web", None) or []
    return [
        {
            "url": r.url or "",
            "title": r.title or "",
            "description": r.description or "",
        }
        for r in items
    ]
