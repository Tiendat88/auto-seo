"""Persistence layer for brand analyses — DB history."""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.brand.models import BrandMonitorResponse
from app.db import Base

log = logging.getLogger(__name__)


class BrandAnalysis(Base):
    __tablename__ = "brand_analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    brand_name: Mapped[str] = mapped_column(String(200))
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Scores
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full analysis payload
    analysis_data: Mapped[dict[str, Any]] = mapped_column(JSON)

    # Metadata
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    providers_used: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    prompt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_brand_name_created", "brand_name", created_at.desc()),
    )


async def save_brand_analysis(
    session: AsyncSession,
    response: BrandMonitorResponse,
    url: str | None = None,
    industry: str | None = None,
) -> BrandAnalysis:
    """Persist a brand analysis result to the database."""
    providers = sorted({a.platform for a in response.platform_analyses})

    analysis = BrandAnalysis(
        brand_name=response.brand_name,
        query=response.query or None,
        url=url,
        industry=industry,
        overall_score=response.scores.overall_score if response.scores else None,
        visibility_score=response.scores.visibility_score if response.scores else None,
        analysis_data=response.model_dump(mode="json"),
        model_used=response.model_used,
        providers_used=providers,
        prompt_count=len(response.queries) if response.queries else 1,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    log.info(
        "Saved brand analysis %s (brand=%s, score=%s)",
        analysis.id, response.brand_name,
        response.scores.overall_score if response.scores else "n/a",
    )
    return analysis


async def get_brand_analysis(
    session: AsyncSession, analysis_id: str,
) -> BrandAnalysis | None:
    """Get a saved brand analysis by ID."""
    return await session.get(BrandAnalysis, analysis_id)


async def list_brand_analyses(
    session: AsyncSession,
    brand_name: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[BrandAnalysis], int]:
    """List brand analyses, optionally filtered by brand name."""
    query = select(BrandAnalysis).order_by(BrandAnalysis.created_at.desc())
    count_query = select(func.count(BrandAnalysis.id))

    if brand_name:
        query = query.where(BrandAnalysis.brand_name == brand_name)
        count_query = count_query.where(BrandAnalysis.brand_name == brand_name)

    total = (await session.execute(count_query)).scalar() or 0
    result = await session.execute(query.offset(offset).limit(limit))
    analyses = list(result.scalars().all())
    return analyses, total
