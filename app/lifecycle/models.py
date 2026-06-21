"""ORM models, phase enum, and API schemas for the SEO lifecycle."""

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.article.models import BrandVoice
from app.config import settings
from app.db import Base


class LifecyclePhase(StrEnum):
    CREATED = "created"              # just created, not yet run
    GENERATING = "generating"        # a Job is running (auto-publishes on completion)
    MONITORING = "monitoring"        # steady state, waiting for next_run_at
    MEASURING = "measuring"          # a measurement pass is running
    NEEDS_REFRESH = "needs_refresh"  # decay detected, queued to regenerate
    PAUSED = "paused"                # user-disabled, scheduler skips
    FAILED = "failed"                # last generation Job failed
    DONE = "done"                    # single-cycle lifecycle finished (terminal)


# Phases the scheduler considers "due" for advancement.
ACTIVE_PHASES = (
    LifecyclePhase.CREATED,
    LifecyclePhase.GENERATING,
    LifecyclePhase.MONITORING,
    LifecyclePhase.NEEDS_REFRESH,
)


class RefreshPolicy(BaseModel):
    """Thresholds that trigger a refresh. Falls back to global settings."""

    rank_threshold: int = Field(default_factory=lambda: settings.lifecycle_rank_threshold)
    aeo_threshold: int = Field(default_factory=lambda: settings.lifecycle_aeo_threshold)
    brand_threshold: float = Field(default_factory=lambda: settings.lifecycle_brand_threshold)
    max_content_age_days: int = Field(
        default_factory=lambda: settings.lifecycle_max_content_age_days
    )


class Lifecycle(Base):
    __tablename__ = "lifecycles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Generation params (copied into each spawned Job)
    topic: Mapped[str] = mapped_column(String(200))
    target_word_count: Mapped[int] = mapped_column(Integer, default=1500)
    language: Mapped[str] = mapped_column(String(2), default="en")
    brand_voice_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # State
    phase: Mapped[str] = mapped_column(String(20), default=LifecyclePhase.CREATED, index=True)
    current_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    published_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cycle_count: Mapped[int] = mapped_column(Integer, default=0)
    cycle_job_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Measurement target
    measure_query: Mapped[str | None] = mapped_column(String(300), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Scheduling (cadence_days == 0 → single-cycle → DONE; > 0 → recurring loop)
    cadence_days: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Latest-snapshot columns (fast reads)
    last_aeo_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_brand_visibility: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Per-lifecycle threshold overrides (falls back to config when null)
    policy_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_lifecycle_enabled_next_run", "enabled", "next_run_at"),
    )

    # --- Helpers ---

    def get_brand_voice(self) -> BrandVoice | None:
        if self.brand_voice_data:
            return BrandVoice.model_validate(self.brand_voice_data)
        return None

    def set_brand_voice(self, data: BrandVoice) -> None:
        self.brand_voice_data = data.model_dump(mode="json")

    def get_policy(self) -> RefreshPolicy:
        return RefreshPolicy.model_validate(self.policy_data or {})

    def set_policy(self, policy: RefreshPolicy) -> None:
        self.policy_data = policy.model_dump(mode="json")

    def append_cycle_job(self, job_id: str) -> None:
        existing = list(self.cycle_job_ids or [])
        existing.append(job_id)
        self.cycle_job_ids = existing
        self.cycle_count = len(existing)


class LifecycleMeasurement(Base):
    __tablename__ = "lifecycle_measurements"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    lifecycle_id: Mapped[str] = mapped_column(String(36), index=True)
    cycle_count: Mapped[int] = mapped_column(Integer, default=0)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    aeo_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aeo_band: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand_visibility: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    decayed: Mapped[bool] = mapped_column(Boolean, default=False)
    decay_reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_lcm_lifecycle_created", "lifecycle_id", created_at.desc()),
    )

    def to_response(self) -> "MeasurementResponse":
        return MeasurementResponse(
            id=self.id,
            lifecycle_id=self.lifecycle_id,
            cycle_count=self.cycle_count,
            job_id=self.job_id,
            aeo_score=self.aeo_score,
            aeo_band=self.aeo_band,
            rank_position=self.rank_position,
            brand_visibility=self.brand_visibility,
            content_age_days=self.content_age_days,
            decayed=self.decayed,
            decay_reasons=self.decay_reasons or [],
            created_at=self.created_at,
        )


# --- API request/response schemas ---


class LifecycleCreateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    target_word_count: int = Field(default=1500, ge=300, le=10000)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    brand_voice: BrandVoice | None = None
    webhook_url: str | None = Field(default=None, max_length=500)
    cadence_days: int = Field(
        default=0, ge=0, le=365,
        description="0 = single cycle (one-shot); > 0 = recurring re-measure cadence in days.",
    )
    measure_query: str | None = Field(default=None, max_length=300)
    brand_name: str | None = Field(default=None, max_length=200)
    policy: RefreshPolicy | None = None
    generate_now: bool = Field(
        default=True, description="Run the first generation cycle immediately."
    )


class LifecycleSummary(BaseModel):
    id: str
    topic: str
    phase: LifecyclePhase
    enabled: bool
    cadence_days: int
    cycle_count: int
    current_job_id: str | None = None
    published_url: str | None = None
    next_run_at: datetime | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class LifecycleResponse(LifecycleSummary):
    target_word_count: int
    language: str
    measure_query: str | None = None
    brand_name: str | None = None
    last_run_at: datetime | None = None
    last_refresh_at: datetime | None = None
    last_aeo_score: int | None = None
    last_rank_position: int | None = None
    last_brand_visibility: float | None = None


class LifecycleListResponse(BaseModel):
    lifecycles: list[LifecycleSummary]
    total: int


class MeasurementResponse(BaseModel):
    id: str
    lifecycle_id: str
    cycle_count: int
    job_id: str | None = None
    aeo_score: int | None = None
    aeo_band: str | None = None
    rank_position: int | None = None
    brand_visibility: float | None = None
    content_age_days: int | None = None
    decayed: bool = False
    decay_reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class MeasurementListResponse(BaseModel):
    measurements: list[MeasurementResponse]
    total: int


class TickResponse(BaseModel):
    advanced: list[str] = Field(default_factory=list)


def to_summary(lc: Lifecycle) -> LifecycleSummary:
    return LifecycleSummary(
        id=lc.id,
        topic=lc.topic,
        phase=LifecyclePhase(lc.phase),
        enabled=lc.enabled,
        cadence_days=lc.cadence_days,
        cycle_count=lc.cycle_count,
        current_job_id=lc.current_job_id,
        published_url=lc.published_url,
        next_run_at=lc.next_run_at,
        error=lc.error,
        created_at=lc.created_at,
        updated_at=lc.updated_at,
    )


def to_response(lc: Lifecycle) -> LifecycleResponse:
    return LifecycleResponse(
        **to_summary(lc).model_dump(),
        target_word_count=lc.target_word_count,
        language=lc.language,
        measure_query=lc.measure_query,
        brand_name=lc.brand_name,
        last_run_at=lc.last_run_at,
        last_refresh_at=lc.last_refresh_at,
        last_aeo_score=lc.last_aeo_score,
        last_rank_position=lc.last_rank_position,
        last_brand_visibility=lc.last_brand_visibility,
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to UTC-aware.

    SQLite (tests) returns naive datetimes from ``DateTime(timezone=True)`` columns while
    Postgres (prod) returns aware ones; this keeps comparisons with ``utcnow()`` safe on both.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
