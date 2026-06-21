"""Fetch AI platform responses for a query via their APIs.

Uses raw SDK clients (not LlmClient) intentionally — the fetcher sends bare
queries with no system prompt, no caching, and no formatting so responses
reflect what a real user would see on each platform.
"""

import asyncio
import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from app.brand.gather import gather_partial
from app.brand.models import PlatformResponse
from app.config import settings
from app.errors import LlmError

log = logging.getLogger(__name__)

_FETCH_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)

async def fetch_platform_responses(
    query: str,
    skip: set[str] | None = None,
    web_search: bool = True,
) -> list[PlatformResponse]:
    """Query configured AI platforms (only LiteLLM now)."""
    skip = skip or set()
    tasks: dict[str, asyncio.Task[PlatformResponse]] = {}

    if settings.litellm_api_key and "chatgpt" not in skip:
        tasks["chatgpt"] = asyncio.create_task(
            _fetch_openai(query, web_search),
        )

    if not tasks:
        raise ValueError(
            "No AI platform API keys configured. "
            "Set LITELLM_API_KEY."
        )

    return await gather_partial(tasks, "API")
