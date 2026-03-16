from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --- Editorial Brief ---


class ArticleBrief(BaseModel):
    target_audience: str
    tone: str
    angle: str
    differentiators: list[str] = Field(default_factory=list)
    content_gaps_to_fill: list[str] = Field(default_factory=list)


# --- Competitive Analysis ---


class KeywordCluster(BaseModel):
    primary: str
    secondary: list[str] = Field(default_factory=list)
    long_tail: list[str] = Field(default_factory=list)


class CompetitorTheme(BaseModel):
    theme: str
    frequency: int = Field(..., ge=1, description="How many top results cover this")
    subtopics: list[str] = Field(default_factory=list)


class ContentGap(BaseModel):
    topic: str
    reason: str


class CompetitiveAnalysis(BaseModel):
    keywords: KeywordCluster
    themes: list[CompetitorTheme] = Field(..., min_length=1)
    content_gaps: list[ContentGap] = Field(default_factory=list)
    avg_word_count: int = Field(..., ge=0)
    common_heading_patterns: list[str] = Field(default_factory=list)
    search_intent: Literal["informational", "transactional", "navigational", "commercial"]


# --- Outline ---


class HeadingLevel(StrEnum):
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"


class OutlineHeading(BaseModel):
    level: HeadingLevel
    text: str
    target_word_count: int = Field(..., ge=30)
    key_points: list[str] = Field(default_factory=list)
    keywords_to_include: list[str] = Field(default_factory=list)


class ArticleOutline(BaseModel):
    h1: str
    headings: list[OutlineHeading] = Field(..., min_length=3)
    estimated_total_words: int
    faq_questions: list[str] = Field(default_factory=list)
    brief: ArticleBrief | None = None


# --- Article Content ---


class ArticleSection(BaseModel):
    heading: str
    heading_level: HeadingLevel
    content: str
    word_count: int = 0

    @model_validator(mode="after")
    def compute_word_count(self) -> "ArticleSection":
        self.word_count = len(self.content.split())
        return self


class FaqItem(BaseModel):
    question: str
    answer: str


class ArticleContent(BaseModel):
    sections: list[ArticleSection] = Field(..., min_length=1)
    faq: list[FaqItem] = Field(default_factory=list)
    total_word_count: int = 0

    @model_validator(mode="after")
    def compute_total(self) -> "ArticleContent":
        section_words = sum(s.word_count for s in self.sections)
        faq_words = sum(len(f.question.split()) + len(f.answer.split()) for f in self.faq)
        self.total_word_count = section_words + faq_words
        return self


# --- SEO ---


class SeoMetadata(BaseModel):
    title_tag: str = Field(..., max_length=60)
    meta_description: str = Field(..., max_length=160)
    primary_keyword: str
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class KeywordUsage(BaseModel):
    keyword: str
    count: int
    density: float
    locations: list[str] = Field(default_factory=list)


class SectionKeywordDensity(BaseModel):
    section_heading: str
    keyword: str
    count: int
    density: float
    word_count: int


class KeywordDistribution(BaseModel):
    primary_by_section: list[SectionKeywordDensity]
    distribution_score: float = Field(..., ge=0.0, le=1.0)


class KeywordAnalysis(BaseModel):
    primary: KeywordUsage
    secondary: list[KeywordUsage] = Field(default_factory=list)
    keyword_distribution: KeywordDistribution | None = None


class InternalLink(BaseModel):
    anchor_text: str
    suggested_target_topic: str
    placement_context: str


class ExternalReference(BaseModel):
    title: str
    url: str
    authority_reason: str
    placement_section: str

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        if not v.startswith(("https://", "http://")):
            raise ValueError("URL must use http or https scheme")
        return v


class LinkSuggestions(BaseModel):
    internal: list[InternalLink] = Field(..., min_length=3, max_length=5)
    external: list[ExternalReference] = Field(..., min_length=2, max_length=4)


# --- SEO Meta Options ---


class SeoMetaOptions(BaseModel):
    title_options: list[str] = Field(..., min_length=5, max_length=5)
    description_options: list[str] = Field(..., min_length=5, max_length=5)


# --- Brand Voice ---


class BrandVoice(BaseModel):
    brand_name: str | None = None
    voice_description: str | None = None
    writing_examples: list[str] = Field(default_factory=list, max_length=3)
    style_notes: str | None = None


# --- Quality ---


class ScoreDimension(BaseModel):
    name: str
    score: float = Field(..., ge=0.0, le=1.0)
    feedback: str


class QualityScore(BaseModel):
    overall: float = Field(..., ge=0.0, le=1.0)
    dimensions: list[ScoreDimension]
    passes_threshold: bool
    revision_instructions: str | None = None


# --- Review ---


class ReviewSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ReviewIssue(BaseModel):
    category: str
    severity: ReviewSeverity
    description: str
    affected_section: str | None = None
    suggestion: str


class ReviewResult(BaseModel):
    passed: bool
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    revision_instructions: str | None = None


# --- Composite Result ---


class TokenUsage(BaseModel):
    """Token consumption for a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    provider: str = ""
    step: str = ""
    model: str = ""

    @model_validator(mode="after")
    def _compute_total(self) -> "TokenUsage":
        if not self.total_tokens:
            self.total_tokens = self.input_tokens + self.output_tokens
        return self


class PipelineEvent(BaseModel):
    """Structured event emitted during pipeline execution."""
    timestamp: str = ""
    step: str = ""
    event: str = ""
    detail: str = ""


class ArticleResult(BaseModel):
    seo_metadata: SeoMetadata
    content: ArticleContent
    keyword_analysis: KeywordAnalysis
    links: LinkSuggestions
    quality: QualityScore
    review: ReviewResult | None = None
    competitive_analysis: CompetitiveAnalysis
    outline: ArticleOutline
    schema_markup: dict[str, Any] | None = None
    meta_options: SeoMetaOptions | None = None
    snippet_opportunities: list[dict[str, Any]] = Field(default_factory=list)
