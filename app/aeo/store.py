"""Persistence layer for AEO: DB history + Redis cache."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.cache import cache, cache_key
from app.db import Base

log = logging.getLogger(__name__)

_FETCH_CACHE_TTL = 7 * 24 * 3600  # 7 days
_FANOUT_CACHE_TTL = 24 * 3600  # 1 day (LLM results change with model updates)


# --- ORM Model ---


class AeoAnalysis(Base):
    __tablename__ = "aeo_analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # What was analyzed
    input_type: Mapped[str] = mapped_column(String(10))  # "url" or "text"
    input_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(16))  # dedup key

    # AEO score results
    aeo_score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(30))
    checks_data: Mapped[list[dict[str, Any]]] = mapped_column(JSON)

    # Fan-out results (nullable — only if fan-out was run)
    target_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    fanout_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Metadata
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_aeo_url_created", "input_url", created_at.desc()),
        Index("ix_aeo_hash", "content_hash"),
    )


# --- Redis Cache: Firecrawl fetches ---


async def get_cached_fetch(url: str) -> dict | None:
    """Get cached Firecrawl fetch result (html + markdown + metadata)."""
    key = cache_key("aeo:fetch", url)
    raw = await cache.get(key)
    if raw:
        log.debug("Cache hit for fetch: %s", url)
        return json.loads(raw)
    return None


async def set_cached_fetch(url: str, result: dict) -> None:
    """Cache Firecrawl fetch result for 7 days."""
    key = cache_key("aeo:fetch", url)
    await cache.set(key, json.dumps(result), ttl=_FETCH_CACHE_TTL)


# --- Redis Cache: Fan-out LLM results ---


async def get_cached_fanout(query: str, model: str) -> dict | None:
    """Get cached fan-out sub-queries for a query+model pair."""
    key = cache_key("aeo:fanout", query.lower().strip(), model)
    raw = await cache.get(key)
    if raw:
        log.debug("Cache hit for fanout: %s", query)
        return json.loads(raw)
    return None


async def set_cached_fanout(query: str, model: str, result: dict) -> None:
    """Cache fan-out LLM result for 1 day."""
    key = cache_key("aeo:fanout", query.lower().strip(), model)
    await cache.set(key, json.dumps(result), ttl=_FANOUT_CACHE_TTL)


# --- DB: Save analysis run ---


async def save_aeo_analysis(
    session: AsyncSession,
    input_type: str,
    input_url: str | None,
    content_hash: str,
    aeo_score: int,
    band: str,
    checks: list[dict],
    target_query: str | None = None,
    fanout_data: dict | None = None,
    model_used: str | None = None,
) -> AeoAnalysis:
    """Persist an AEO analysis run to the database."""
    analysis = AeoAnalysis(
        input_type=input_type,
        input_url=input_url,
        content_hash=content_hash,
        aeo_score=aeo_score,
        band=band,
        checks_data=checks,
        target_query=target_query,
        fanout_data=fanout_data,
        model_used=model_used,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    log.info("Saved AEO analysis %s (score=%d, url=%s)", analysis.id, aeo_score, input_url)
    return analysis
