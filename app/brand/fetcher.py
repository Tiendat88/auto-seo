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


@_FETCH_RETRY
async def _fetch_perplexity(query: str) -> PlatformResponse:
    """Query Perplexity sonar model (always search-grounded)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.perplexity_api_key,
        base_url="https://api.perplexity.ai",
    )
    response = await client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": query}],
    )
    text = response.choices[0].message.content or ""
    if not text:
        raise LlmError("Empty response from Perplexity")
    log.info("Perplexity response: %d chars", len(text))
    return PlatformResponse(platform="perplexity", response_text=text)


@_FETCH_RETRY
async def _fetch_openai(
    query: str, web_search: bool = True,
) -> PlatformResponse:
    """Query OpenAI ChatGPT, optionally with web search grounding."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    kwargs: dict = {
        "model": "gpt-4o-mini-search-preview" if web_search else "gpt-4o-mini",
        "messages": [{"role": "user", "content": query}],
    }
    if web_search:
        kwargs["web_search_options"] = {}

    response = await client.chat.completions.create(**kwargs)
    text = response.choices[0].message.content or ""
    if not text:
        raise LlmError("Empty response from OpenAI")
    log.info("OpenAI response: %d chars", len(text))
    return PlatformResponse(platform="chatgpt", response_text=text)


@_FETCH_RETRY
async def _fetch_gemini(
    query: str, web_search: bool = True,
) -> PlatformResponse:
    """Query Google Gemini, optionally with search grounding."""
    from google import genai  # type: ignore[reportAttributeAccessIssue]
    from google.genai import types  # type: ignore[reportAttributeAccessIssue]

    client = genai.Client(api_key=settings.google_api_key)
    config_kwargs: dict = {}
    if web_search:
        config_kwargs["tools"] = [
            types.Tool(google_search=types.GoogleSearch()),
        ]

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=query,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    text = response.text or ""
    if not text:
        raise LlmError("Empty response from Gemini")
    log.info("Gemini response: %d chars", len(text))
    return PlatformResponse(platform="gemini", response_text=text)


@_FETCH_RETRY
async def _fetch_anthropic(
    query: str, web_search: bool = True,
) -> PlatformResponse:
    """Query Anthropic Claude, optionally with web search tool."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = {
        "model": settings.llm_model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": query}],
    }
    if web_search:
        kwargs["tools"] = [
            {"type": "web_search_20250305", "max_uses": 3},
        ]

    response = await client.messages.create(**kwargs)
    text = "".join(
        b.text for b in response.content if hasattr(b, "text")
    )
    if not text:
        raise LlmError("Empty response from Anthropic")
    log.info("Anthropic response: %d chars", len(text))
    return PlatformResponse(platform="claude", response_text=text)


async def fetch_platform_responses(
    query: str,
    skip: set[str] | None = None,
    web_search: bool = True,
) -> list[PlatformResponse]:
    """Query configured AI platforms in parallel, skipping any in `skip`."""
    skip = skip or set()
    tasks: dict[str, asyncio.Task[PlatformResponse]] = {}

    if settings.perplexity_api_key and "perplexity" not in skip:
        tasks["perplexity"] = asyncio.create_task(
            _fetch_perplexity(query),
        )
    if settings.openai_api_key and "chatgpt" not in skip:
        tasks["chatgpt"] = asyncio.create_task(
            _fetch_openai(query, web_search),
        )
    if settings.google_api_key and "gemini" not in skip:
        tasks["gemini"] = asyncio.create_task(
            _fetch_gemini(query, web_search),
        )
    if settings.anthropic_api_key and "claude" not in skip:
        tasks["claude"] = asyncio.create_task(
            _fetch_anthropic(query, web_search),
        )

    if not tasks:
        raise ValueError(
            "No AI platform API keys configured. "
            "Set PERPLEXITY_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, "
            "or ANTHROPIC_API_KEY."
        )

    return await gather_partial(tasks, "API")
