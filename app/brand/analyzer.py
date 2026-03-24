"""Brand Monitor service — isolated per-platform LLM analysis."""

import asyncio
import logging
from collections import Counter

from app.brand.models import (
    AggregateSummary,
    BrandMonitorRequest,
    BrandMonitorResponse,
    LLMBrandAnalysis,
    MentionContext,
    PlatformAnalysis,
    Sentiment,
)
from app.llm import LlmClient

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def build_prompt(
    brand_name: str, query: str, response_text: str, keywords: list[str],
) -> str:
    """Build the analysis prompt. Pure function — easy to test and inspect."""
    keywords_block = ""
    if keywords:
        terms = ", ".join(f'"{k}"' for k in keywords)
        keywords_block = (
            f"\nIn addition to any brands/products you discover, "
            f"check specifically for these terms: {terms}.\n"
        )

    return f"""You are a brand mention analyst. Analyze ONLY the provided text.

Brand to monitor: "{brand_name}"
Original user query: "{query}"
{keywords_block}
AI Platform Response:
---
{response_text}
---

Extract structured data about how "{brand_name}" appears in this response.

Rules:
- "mention_context": "recommended" if top pick, "compared" if alongside \
alternatives, "referenced" if named but not evaluated, "not_mentioned" if absent.
- "brand_position": the brand's rank in any list (1 = first/top pick). \
null if no list or brand not listed.
- "sentiment.overall": positive/neutral/negative toward the brand.
- "sentiment.reasoning": 1-2 sentences explaining why, citing text signals.
- "sentiment.aspects": per-feature breakdown. Extract each feature/strength/weakness \
attributed to {brand_name}. Each has a feature name, sentiment, and brief detail.
- "competitors[].position": their rank in the list (1 = first mentioned).
- "relevant_quotes": exact text from the response mentioning {brand_name}. Max 5.
- "keywords_found": all brand/product names in the text.
- Base analysis strictly on the provided text. No external knowledge.

Example for brand "Notion" with query "best note-taking app":
{{
  "brand_mentioned": true,
  "mention_context": "recommended",
  "brand_position": 1,
  "sentiment": {{
    "overall": "positive",
    "reasoning": "Listed as #1 pick, praised for versatility and free student plan.",
    "aspects": [
      {{"feature": "collaboration", "sentiment": "positive", \
"detail": "Praised for team workspaces and shared databases."}},
      {{"feature": "learning curve", "sentiment": "negative", \
"detail": "Described as having a steeper learning curve than alternatives."}}
    ]
  }},
  "keywords_found": ["Notion", "Obsidian", "Evernote"],
  "competitors": [
    {{"name": "Obsidian", "recommended": false, "position": 2}},
    {{"name": "Evernote", "recommended": false, "position": 3}}
  ],
  "relevant_quotes": [
    "Notion is the ultimate all-in-one workspace for students.",
    "Free Plus plan with a .edu email."
  ]
}}"""


# ---------------------------------------------------------------------------
# Per-platform analysis (isolated)
# ---------------------------------------------------------------------------


async def analyze_platform(
    llm: LlmClient,
    brand_name: str,
    query: str,
    platform: str,
    response_text: str,
    keywords: list[str],
) -> PlatformAnalysis:
    """Analyze a single platform response in isolation via generate_structured."""
    prompt = build_prompt(brand_name, query, response_text, keywords)
    result = await llm.generate_structured(
        prompt, LLMBrandAnalysis,
    )

    return PlatformAnalysis(platform=platform, **result.model_dump())


# ---------------------------------------------------------------------------
# Aggregation (pure, no LLM)
# ---------------------------------------------------------------------------


def compute_aggregate(analyses: list[PlatformAnalysis]) -> AggregateSummary:
    """Aggregate per-platform results."""
    if not analyses:
        return AggregateSummary(
            platforms_mentioning_brand=0,
            total_platforms=0,
            overall_sentiment=Sentiment.NEUTRAL,
            top_competitors=[],
            brand_recommended_on=[],
            all_keywords_found=[],
        )

    mentioning = [a for a in analyses if a.brand_mentioned]

    # Majority-vote sentiment, positive wins ties
    sentiment_counts: dict[Sentiment, int] = {s: 0 for s in Sentiment}
    for a in analyses:
        sentiment_counts[a.sentiment.overall] += 1
    priority = [Sentiment.POSITIVE, Sentiment.NEUTRAL, Sentiment.NEGATIVE]
    overall_sentiment = max(
        priority,
        key=lambda s: (sentiment_counts[s], -priority.index(s)),
    )

    # Average brand position across platforms that listed it
    positions = [
        a.brand_position for a in analyses if a.brand_position is not None
    ]
    avg_position = round(sum(positions) / len(positions), 1) if positions else None

    # Competitors sorted by cross-platform frequency
    freq: dict[str, int] = {}
    for a in analyses:
        for c in a.competitors:
            freq[c.name] = freq.get(c.name, 0) + 1
    top_competitors = sorted(freq, key=lambda n: freq[n], reverse=True)

    # Platforms where brand was recommended
    brand_recommended_on = [
        a.platform
        for a in analyses
        if a.mention_context == MentionContext.RECOMMENDED
    ]

    # Deduplicated keywords union
    all_keywords: list[str] = []
    seen_kw: set[str] = set()
    for a in analyses:
        for kw in a.keywords_found:
            key = kw.lower()
            if key not in seen_kw:
                seen_kw.add(key)
                all_keywords.append(kw)

    # Cross-platform feature analysis
    strength_counts: Counter[str] = Counter()
    weakness_counts: Counter[str] = Counter()
    for a in analyses:
        for aspect in a.sentiment.aspects:
            key = aspect.feature.lower()
            if aspect.sentiment == Sentiment.POSITIVE:
                strength_counts[key] += 1
            elif aspect.sentiment == Sentiment.NEGATIVE:
                weakness_counts[key] += 1

    # Features mentioned on 2+ platforms
    common_strengths = [
        f for f, c in strength_counts.most_common() if c >= 2
    ]
    common_weaknesses = [
        f for f, c in weakness_counts.most_common() if c >= 2
    ]
    # If fewer than 2 platforms, include anything mentioned
    if len(analyses) < 3:
        common_strengths = [f for f, _ in strength_counts.most_common()]
        common_weaknesses = [f for f, _ in weakness_counts.most_common()]

    return AggregateSummary(
        platforms_mentioning_brand=len(mentioning),
        total_platforms=len(analyses),
        overall_sentiment=overall_sentiment,
        avg_brand_position=avg_position,
        top_competitors=top_competitors,
        brand_recommended_on=brand_recommended_on,
        all_keywords_found=all_keywords,
        common_strengths=common_strengths,
        common_weaknesses=common_weaknesses,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def analyze_brand(
    request: BrandMonitorRequest, llm: LlmClient | None = None,
) -> BrandMonitorResponse:
    """Analyze brand mentions across platforms. Each gets an isolated LLM call."""
    if llm is None:
        llm = LlmClient()

    tasks = [
        analyze_platform(
            llm=llm,
            brand_name=request.brand_name,
            query=request.query,
            platform=pr.platform,
            response_text=pr.response_text,
            keywords=request.keywords,
        )
        for pr in request.platform_responses
    ]
    analyses = list(await asyncio.gather(*tasks))

    usage = llm.drain_usage()
    if usage:
        total_cost = sum(u.cost for u in usage)
        total_tokens = sum(u.input_tokens + u.output_tokens for u in usage)
        log.info(
            "Brand monitor: %d tokens across %d calls, $%.4f",
            total_tokens, len(usage), total_cost,
        )

    aggregate = compute_aggregate(analyses)

    return BrandMonitorResponse(
        brand_name=request.brand_name,
        query=request.query,
        model_used=llm.model_name,
        platform_analyses=analyses,
        aggregate=aggregate,
    )
