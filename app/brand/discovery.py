"""Brand discovery — scrape website, identify competitors, generate prompts.

Auto-populates brand analysis inputs from a single URL.
"""

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from app.config import settings
from app.errors import ContentFetchError
from app.llm import LlmClient
from app.serp.fetcher import fetch_page_content

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas for LLM structured output
# ---------------------------------------------------------------------------


class CompanyInfo(BaseModel):
    """Extracted company metadata from website content."""

    name: str
    description: str = Field(..., max_length=500)
    industry: str
    keywords: list[str] = Field(default=[], max_length=20)
    main_products: list[str] = Field(default=[], max_length=10)
    known_competitors: list[str] = Field(default=[], max_length=10)


class IdentifiedCompetitor(BaseModel):
    """A competitor identified by the LLM."""

    name: str
    competitor_type: str = Field(
        ..., description="'direct' or 'indirect'",
    )
    market_overlap: str = Field(
        ..., description="'high', 'medium', or 'low'",
    )
    confidence: float = Field(ge=0, le=1)


class CompetitorDiscovery(BaseModel):
    """LLM output schema for competitor identification."""

    competitors: list[IdentifiedCompetitor]


class PromptCategory(StrEnum):
    RANKING = "ranking"
    COMPARISON = "comparison"
    ALTERNATIVES = "alternatives"
    RECOMMENDATIONS = "recommendations"


class GeneratedPrompt(BaseModel):
    """A generated brand monitoring prompt."""

    category: PromptCategory
    prompt: str


# ---------------------------------------------------------------------------
# URL scraping + company info extraction
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """\
You are a business analyst. Extract structured company information \
from the following website content.

Website content:
---
{content}
---

Extract:
- name: the company/product name
- description: 1-2 sentence description of what the company does
- industry: the primary industry or category \
(e.g. "project management", "note-taking", "web scraping")
- keywords: up to 20 relevant keywords/terms about the product
- main_products: the primary products or services offered (up to 10)
- known_competitors: any competitors mentioned or implied (up to 10)

Be precise and factual — only extract what is stated or clearly implied."""


async def scrape_company_info(url: str, llm: LlmClient) -> CompanyInfo:
    """Scrape a URL via Firecrawl and extract company metadata via LLM.

    Raises ``ContentFetchError`` if scraping fails,
    ``LlmError`` if extraction fails.
    """
    if not settings.firecrawl_api_key:
        raise ContentFetchError(
            "FIRECRAWL_API_KEY is required for URL-based brand discovery."
        )

    try:
        content, word_count = await fetch_page_content(url, max_chars=15000)
    except Exception as exc:
        raise ContentFetchError(f"Failed to scrape {url}: {exc}") from exc

    if word_count < 10:
        raise ContentFetchError(
            f"Scraped content from {url} is too short ({word_count} words)."
        )

    log.info("Scraped %s: %d words", url, word_count)

    prompt = _EXTRACT_PROMPT.format(content=content)
    return await llm.generate_structured(prompt, CompanyInfo, use_cache=False)


# ---------------------------------------------------------------------------
# Competitor identification
# ---------------------------------------------------------------------------

_COMPETITOR_PROMPT = """You are a competitive intelligence analyst.

Company: {name}
Industry: {industry}
Description: {description}
Products: {products}
Known competitors: {known}

Identify 6-9 direct competitors for this company. For each competitor, specify:
- name: the competitor company/product name
- competitor_type: "direct" (same market) or "indirect" (adjacent market)
- market_overlap: "high", "medium", or "low"
- confidence: 0.0 to 1.0 — how confident you are this is a real competitor

Focus on well-known, real companies. Prefer direct competitors with high market overlap.
Do not repeat the company itself or competitors already listed."""


async def identify_competitors(
    company: CompanyInfo, llm: LlmClient,
) -> list[IdentifiedCompetitor]:
    """Use LLM to identify direct competitors for a company."""
    known = ", ".join(company.known_competitors) if company.known_competitors else "none"
    products = ", ".join(company.main_products) if company.main_products else "unknown"

    prompt = _COMPETITOR_PROMPT.format(
        name=company.name,
        industry=company.industry,
        description=company.description,
        products=products,
        known=known,
    )

    result = await llm.generate_structured(prompt, CompetitorDiscovery, use_cache=False)

    # Merge with known competitors (deduplicate)
    seen = {c.name.lower() for c in result.competitors}
    for name in company.known_competitors:
        if name.lower() not in seen:
            seen.add(name.lower())
            result.competitors.append(IdentifiedCompetitor(
                name=name,
                competitor_type="direct",
                market_overlap="high",
                confidence=0.8,
            ))

    # Filter: keep direct + high/medium overlap, cap at 9
    filtered = [
        c for c in result.competitors
        if c.competitor_type == "direct" and c.market_overlap in ("high", "medium")
    ]

    # If too few direct, include indirect high-overlap
    if len(filtered) < 4:
        for c in result.competitors:
            if c not in filtered and c.market_overlap == "high":
                filtered.append(c)

    return filtered[:9]


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

_RANKING_TEMPLATES = [
    "What are the top 10 {industry} tools right now?",
    "What are the best {industry} solutions available today?",
    "Which {industry} platforms are most popular right now?",
    "Rank the best {industry} tools for businesses.",
]

_COMPARISON_TEMPLATES = [
    "{brand} vs {competitor}: which is better for {industry}?",
    "How does {brand} compare to {competitor}?",
    "Compare {brand} and {competitor} for {use_case}.",
]

_ALTERNATIVES_TEMPLATES = [
    "What are the best alternatives to {brand}?",
    "I'm looking for alternatives to {brand}. What do you recommend?",
    "What should I use instead of {brand}?",
]

_RECOMMENDATIONS_TEMPLATES = [
    "What {industry} tool would you recommend for a small business?",
    "I need a {industry} solution. What should I choose?",
    "What's the best {industry} platform for teams?",
    "Recommend a {industry} tool for {use_case}.",
]


def generate_brand_prompts(
    company: CompanyInfo,
    competitors: list[str],
    max_prompts: int = 14,
) -> list[GeneratedPrompt]:
    """Generate targeted brand monitoring prompts across 4 categories.

    Pure function — no LLM calls. Uses templates with company context.
    """
    prompts: list[GeneratedPrompt] = []
    industry = company.industry
    brand = company.name

    # Use first product or industry as use_case
    use_case = company.main_products[0] if company.main_products else industry

    # Ranking (3-4 prompts)
    for template in _RANKING_TEMPLATES[:3]:
        prompts.append(GeneratedPrompt(
            category=PromptCategory.RANKING,
            prompt=template.format(industry=industry, brand=brand),
        ))

    # Comparison (3-4 prompts, one per top competitor)
    for i, competitor in enumerate(competitors[:3]):
        template = _COMPARISON_TEMPLATES[i % len(_COMPARISON_TEMPLATES)]
        prompts.append(GeneratedPrompt(
            category=PromptCategory.COMPARISON,
            prompt=template.format(
                brand=brand, competitor=competitor,
                industry=industry, use_case=use_case,
            ),
        ))

    # Alternatives (2-3 prompts)
    for template in _ALTERNATIVES_TEMPLATES[:3]:
        prompts.append(GeneratedPrompt(
            category=PromptCategory.ALTERNATIVES,
            prompt=template.format(brand=brand),
        ))

    # Recommendations (3-4 prompts)
    for template in _RECOMMENDATIONS_TEMPLATES[:3]:
        prompts.append(GeneratedPrompt(
            category=PromptCategory.RECOMMENDATIONS,
            prompt=template.format(
                industry=industry, brand=brand, use_case=use_case,
            ),
        ))

    return prompts[:max_prompts]
