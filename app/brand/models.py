"""Brand Monitor Pydantic models."""

from enum import StrEnum

from pydantic import BaseModel, Field


class MentionContext(StrEnum):
    RECOMMENDED = "recommended"
    COMPARED = "compared"
    REFERENCED = "referenced"
    NOT_MENTIONED = "not_mentioned"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


# --- Request ---


class PlatformResponse(BaseModel):
    platform: str = Field(..., examples=["chatgpt", "perplexity", "gemini", "grok"])
    response_text: str = Field(..., min_length=1, max_length=50_000)


class FetchMode(StrEnum):
    API = "api"
    BROWSER = "browser"


class BrandMonitorRequest(BaseModel):
    brand_name: str = Field(..., min_length=1, examples=["Notion"])
    query: str = Field(..., min_length=1, examples=["best note-taking app"])
    keywords: list[str] = Field(default=[], examples=[["Obsidian", "Evernote"]])
    fetch_mode: FetchMode = Field(
        default=FetchMode.BROWSER,
        description=(
            "'browser' uses Playwright (default; no keys needed), "
            "'api' uses provider APIs."
        ),
    )
    platform_responses: list[PlatformResponse] = Field(
        default=[],
        description=(
            "Optional pre-fetched AI platform responses. "
            "Auto-fetched responses from configured providers are always included."
        ),
    )


# --- LLM structured output schema ---


class CompetitorMention(BaseModel):
    name: str
    recommended: bool
    position: int | None = Field(
        None, description="Rank in the response list (1 = first mentioned).",
    )


class FeatureAttribution(BaseModel):
    """A strength or weakness attributed to the brand in the response."""

    feature: str = Field(..., description="Feature name, e.g. 'collaboration'.")
    sentiment: Sentiment
    detail: str = Field(..., description="Brief explanation from the text.")


class SentimentBreakdown(BaseModel):
    """Per-aspect sentiment with reasoning."""

    overall: Sentiment
    reasoning: str = Field(
        ..., description="Why this sentiment, citing specific text signals.",
    )
    aspects: list[FeatureAttribution] = Field(
        default=[],
        description="Per-feature sentiment breakdown.",
    )


class LLMBrandAnalysis(BaseModel):
    """Schema for generate_structured — validates LLM JSON output."""

    brand_mentioned: bool
    mention_context: MentionContext
    brand_position: int | None = Field(
        None,
        description=(
            "Brand's rank in the response (1 = first/top pick). "
            "null if not listed or not applicable."
        ),
    )
    sentiment: SentimentBreakdown
    keywords_found: list[str]
    competitors: list[CompetitorMention]
    relevant_quotes: list[str]


# --- Response ---


class PlatformAnalysis(LLMBrandAnalysis):
    """LLM analysis result enriched with the platform name."""

    platform: str


class AggregateSummary(BaseModel):
    platforms_mentioning_brand: int
    total_platforms: int
    overall_sentiment: Sentiment
    avg_brand_position: float | None = Field(
        None, description="Average rank across platforms (lower is better).",
    )
    top_competitors: list[str]
    brand_recommended_on: list[str]
    all_keywords_found: list[str]
    common_strengths: list[str] = Field(
        default=[],
        description="Features praised across multiple platforms.",
    )
    common_weaknesses: list[str] = Field(
        default=[],
        description="Features criticized across multiple platforms.",
    )


class BrandMonitorResponse(BaseModel):
    brand_name: str
    query: str
    model_used: str
    platform_analyses: list[PlatformAnalysis]
    aggregate: AggregateSummary
