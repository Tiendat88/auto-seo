import logging
from datetime import datetime, timezone
from typing import Protocol

import httpx
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.cache import cache, cache_key
from app.errors import SerpError
from app.serp.models import SerpData, SerpQuestion, SerpResult

log = logging.getLogger(__name__)

SERP_CACHE_TTL = 86400  # 24 hours


class SerpProvider(Protocol):
    async def search(self, query: str) -> SerpData: ...


class MockSerpProvider:
    """Generates realistic mock SERP data based on the query topic."""

    async def search(self, query: str) -> SerpData:
        words = query.lower().split()
        slug = "-".join(words[:4])

        domains = [
            "blog.hubspot.com",
            "www.forbes.com",
            "www.techradar.com",
            "zapier.com",
            "www.pcmag.com",
            "www.g2.com",
            "monday.com",
            "asana.com",
            "www.businessnewsdaily.com",
            "www.capterra.com",
        ]

        templates = [
            "15 Best {topic} in 2025 | Complete Guide",
            "{topic}: Top Picks for Teams & Individuals",
            "The Ultimate Guide to {topic} (2025 Edition)",
            "{topic} - Reviews, Pricing & Features",
            "How to Choose the Right {topic} for Your Business",
            "10 {topic} That Actually Work in 2025",
            "{topic}: Expert Recommendations & Comparisons",
            "Best {topic} - Tested & Reviewed by Experts",
            "A Complete Buyer's Guide to {topic}",
            "{topic} Comparison: Find Your Perfect Match",
        ]

        snippet_templates = [
            "Discover the top {topic} that help teams collaborate "
            "effectively. We reviewed and compared the leading options "
            "to help you choose.",
            "Looking for the best {topic}? Our experts tested dozens "
            "of options and narrowed it down to these top picks for 2025.",
            "Compare features, pricing, and user reviews for the most "
            "popular {topic}. Find the perfect fit for your workflow.",
            "From project management to communication, these {topic} "
            "cover everything your team needs to stay productive.",
            "Our in-depth analysis of {topic} includes hands-on testing, "
            "pricing breakdowns, and real user feedback.",
            "Struggling to find the right {topic}? This guide breaks "
            "down the top options by use case, budget, and team size.",
            "The best {topic} offer seamless integration, intuitive "
            "interfaces, and robust feature sets. Here are our top "
            "recommendations.",
            "We surveyed 500+ professionals to find out which {topic} "
            "they rely on daily. Here are the results.",
            "Whether you're a startup or enterprise, these {topic} "
            "scale with your needs. See our detailed comparisons.",
            "Cut through the noise with our expert-curated list of "
            "{topic}. Updated monthly with the latest features and "
            "pricing.",
        ]

        topic_title = query.title()
        results = [
            SerpResult(
                rank=i + 1,
                url=f"https://{domains[i]}/{slug}-guide",
                title=templates[i].format(topic=topic_title),
                snippet=snippet_templates[i].format(topic=query),
            )
            for i in range(10)
        ]

        questions = [
            SerpQuestion(question=f"What are the best {query}?", source="paa"),
            SerpQuestion(question=f"How do I choose {query}?", source="paa"),
            SerpQuestion(question=f"Are {query} worth the investment?", source="paa"),
            SerpQuestion(question=f"What features should I look for in {query}?", source="paa"),
            SerpQuestion(question=f"How much do {query} typically cost?", source="paa"),
        ]

        return SerpData(
            query=query,
            results=results,
            questions=questions,
            fetched_at=datetime.now(timezone.utc),
        )


class SerpApiProvider:
    """Real SerpAPI integration."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise SerpError("SERPAPI_KEY is required for real SERP provider")
        self._api_key = api_key

    async def search(self, query: str) -> SerpData:
        ck = cache_key("serp", query.lower().strip())
        cached = await cache.get(ck)
        if cached:
            try:
                log.info("SERP cache hit for query=%s", query)
                return SerpData.model_validate_json(cached)
            except ValidationError:
                log.warning("Stale SERP cache for query=%s, refetching", query)
                await cache.invalidate(ck)

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _fetch() -> dict:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://serpapi.com/search",
                    params={
                        "q": query,
                        "api_key": self._api_key,
                        "engine": "google",
                        "num": 10,
                    },
                )
                resp.raise_for_status()
                return resp.json()

        try:
            data = await _fetch()
        except httpx.HTTPStatusError as e:
            raise SerpError(
                f"SerpAPI request failed: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise SerpError(f"SerpAPI connection error: {e}") from e

        organic = data.get("organic_results", [])
        results = [
            SerpResult(
                rank=i + 1,
                url=r.get("link", ""),
                title=r.get("title", ""),
                snippet=r.get("snippet", ""),
            )
            for i, r in enumerate(organic[:10])
            if r.get("link")
        ]

        if not results:
            raise SerpError(f"No organic results found for query: {query}")

        questions = []
        for q in data.get("related_questions", []):
            questions.append(SerpQuestion(question=q.get("question", ""), source="paa"))

        serp = SerpData(
            query=query,
            results=results,
            questions=questions,
            fetched_at=datetime.now(timezone.utc),
        )

        await cache.set(ck, serp.model_dump_json(), ttl=SERP_CACHE_TTL)
        return serp


def get_serp_provider(provider: str = "", api_key: str = "") -> SerpProvider:
    """Factory for SERP providers."""
    from app.config import settings

    p = provider or settings.serp_provider
    if p == "serpapi":
        return SerpApiProvider(api_key=api_key or settings.serpapi_key)
    if p == "mock":
        return MockSerpProvider()
    raise SerpError(f"Unknown SERP provider: {p!r}. Use 'serpapi' or 'mock'.")
