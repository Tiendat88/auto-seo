import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.article.models import (
    ArticleContent,
    ArticleOutline,
    ArticleResult,
    BrandVoice,
    CompetitiveAnalysis,
    KeywordAnalysis,
    LinkSuggestions,
    QualityScore,
    ReviewResult,
    SeoMetadata,
    SeoMetaOptions,
    TokenUsage,
)
from app.db import Base
from app.serp.models import SerpData


class JobStatus(StrEnum):
    PENDING = "pending"
    RESEARCHING = "researching"
    PLANNING = "planning"
    GENERATING = "generating"
    SCORING = "scoring"
    REVIEWING = "reviewing"
    EDITING = "editing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    topic: Mapped[str] = mapped_column(String(200))
    target_word_count: Mapped[int] = mapped_column(Integer, default=1500)
    language: Mapped[str] = mapped_column(String(2), default="en")

    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING)
    current_step: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)

    # Intermediate results (JSON, nullable)
    serp_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    analysis_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    outline_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    article_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    seo_metadata_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    keyword_analysis_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    links_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quality_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    review_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    meta_options_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    brand_voice_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usage_data: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    events_data: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_jobs_status_created", "status", created_at.desc()),
    )

    # --- Pydantic serialization helpers ---

    def get_serp(self) -> SerpData | None:
        return SerpData.model_validate(self.serp_data) if self.serp_data else None

    def set_serp(self, data: SerpData) -> None:
        self.serp_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_analysis(self) -> CompetitiveAnalysis | None:
        if self.analysis_data:
            return CompetitiveAnalysis.model_validate(self.analysis_data)
        return None

    def set_analysis(self, data: CompetitiveAnalysis) -> None:
        self.analysis_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_outline(self) -> ArticleOutline | None:
        return ArticleOutline.model_validate(self.outline_data) if self.outline_data else None

    def set_outline(self, data: ArticleOutline) -> None:
        self.outline_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_article(self) -> ArticleContent | None:
        return ArticleContent.model_validate(self.article_data) if self.article_data else None

    def set_article(self, data: ArticleContent) -> None:
        self.article_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_seo_metadata(self) -> SeoMetadata | None:
        if self.seo_metadata_data:
            return SeoMetadata.model_validate(self.seo_metadata_data)
        return None

    def set_seo_metadata(self, data: SeoMetadata) -> None:
        self.seo_metadata_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_keyword_analysis(self) -> KeywordAnalysis | None:
        return (
            KeywordAnalysis.model_validate(self.keyword_analysis_data)
            if self.keyword_analysis_data
            else None
        )

    def set_keyword_analysis(self, data: KeywordAnalysis) -> None:
        self.keyword_analysis_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_links(self) -> LinkSuggestions | None:
        return LinkSuggestions.model_validate(self.links_data) if self.links_data else None

    def set_links(self, data: LinkSuggestions) -> None:
        self.links_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_quality(self) -> QualityScore | None:
        return QualityScore.model_validate(self.quality_data) if self.quality_data else None

    def set_quality(self, data: QualityScore) -> None:
        self.quality_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_review(self) -> ReviewResult | None:
        return ReviewResult.model_validate(self.review_data) if self.review_data else None

    def set_review(self, data: ReviewResult) -> None:
        self.review_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_meta_options(self) -> SeoMetaOptions | None:
        if self.meta_options_data:
            return SeoMetaOptions.model_validate(self.meta_options_data)
        return None

    def set_meta_options(self, data: SeoMetaOptions) -> None:
        self.meta_options_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_brand_voice(self) -> BrandVoice | None:
        if self.brand_voice_data:
            return BrandVoice.model_validate(self.brand_voice_data)
        return None

    def set_brand_voice(self, data: BrandVoice) -> None:
        self.brand_voice_data = data.model_dump(mode="json")
        self.updated_at = datetime.now(timezone.utc)

    def get_usage(self) -> list[TokenUsage]:
        if self.usage_data:
            return [TokenUsage.model_validate(u) for u in self.usage_data]
        return []

    def append_usage(self, items: list[TokenUsage]) -> None:
        existing = self.usage_data or []
        existing.extend(u.model_dump(mode="json") for u in items)
        self.usage_data = existing

    def append_event(self, step: str, event: str, detail: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step, "event": event, "detail": detail,
        }
        existing = self.events_data or []
        existing.append(entry)
        self.events_data = existing

    def build_result(self) -> ArticleResult | None:
        """Build composite result from all intermediate data. Returns None if incomplete."""
        seo = self.get_seo_metadata()
        content = self.get_article()
        keywords = self.get_keyword_analysis()
        links = self.get_links()
        quality = self.get_quality()
        analysis = self.get_analysis()
        outline = self.get_outline()
        if not all([seo, content, keywords, links, quality, analysis, outline]):
            return None

        # Lazily compute schema markup and snippet opportunities
        from app.article.schema import (
            detect_snippet_opportunities,
            generate_schema_markup,
        )

        schema = generate_schema_markup(content, seo, outline)  # type: ignore[arg-type]
        snippets = detect_snippet_opportunities(content, analysis)  # type: ignore[arg-type]
        meta_opts = self.get_meta_options()

        return ArticleResult(
            seo_metadata=seo,  # type: ignore[arg-type]
            content=content,  # type: ignore[arg-type]
            keyword_analysis=keywords,  # type: ignore[arg-type]
            links=links,  # type: ignore[arg-type]
            quality=quality,  # type: ignore[arg-type]
            review=self.get_review(),
            competitive_analysis=analysis,  # type: ignore[arg-type]
            outline=outline,  # type: ignore[arg-type]
            schema_markup=schema.model_dump(),
            meta_options=meta_opts,
            snippet_opportunities=[s.model_dump() for s in snippets],
        )


# --- API Request/Response schemas ---


class ArticleRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    target_word_count: int = Field(default=1500, ge=300, le=10000)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    brand_voice: BrandVoice | None = None


class JobSummaryResponse(BaseModel):
    job_id: str
    status: JobStatus
    topic: str
    target_word_count: int
    language: str
    current_step: str | None = None
    error: str | None = None
    revision_count: int = 0
    created_at: datetime
    updated_at: datetime


class JobResponse(JobSummaryResponse):
    result: ArticleResult | None = None
    serp_data: SerpData | None = None
    analysis_data: CompetitiveAnalysis | None = None
    outline_data: ArticleOutline | None = None
    article_data: ArticleContent | None = None
    quality_data: QualityScore | None = None
    review_data: ReviewResult | None = None
    usage_data: list[dict[str, Any]] | None = None
    events_data: list[dict[str, Any]] | None = None


class JobListResponse(BaseModel):
    jobs: list[JobSummaryResponse]
    total: int
