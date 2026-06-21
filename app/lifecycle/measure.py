"""Measurement subsystem: score a lifecycle's content across 4 decay signals.

Reuses the existing AEO checks, SERP client, and brand scoring — no new scoring math.
"""

import logging
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.aeo.checks import (
    check_direct_answer,
    check_htag_hierarchy,
    check_readability,
    compute_aeo_score,
)
from app.aeo.parser import ParsedContent, get_content, parse_content
from app.job.models import Job
from app.lifecycle.models import (
    Lifecycle,
    LifecycleMeasurement,
    RefreshPolicy,
    ensure_aware,
)
from app.llm import LlmClient
from app.publish.service import _article_to_markdown
from app.serp.client import SerpProvider

log = logging.getLogger(__name__)


def decide_refresh(
    *,
    rank: int | None,
    aeo: int | None,
    brand: float | None,
    age_days: int | None,
    policy: RefreshPolicy,
) -> tuple[bool, list[str]]:
    """Pure decision: is the content decayed? Returns (decayed, reasons)."""
    reasons: list[str] = []
    if rank is not None and rank > policy.rank_threshold:
        reasons.append(f"rank_drop:{rank}>{policy.rank_threshold}")
    if aeo is not None and aeo < policy.aeo_threshold:
        reasons.append(f"aeo_low:{aeo}<{policy.aeo_threshold}")
    if brand is not None and brand < policy.brand_threshold:
        reasons.append(f"brand_low:{brand}<{policy.brand_threshold}")
    if age_days is not None and age_days >= policy.max_content_age_days:
        reasons.append(f"stale:{age_days}>={policy.max_content_age_days}")
    return bool(reasons), reasons


async def _resolve_content(lc: Lifecycle, job: Job | None) -> ParsedContent | None:
    """Prefer the live published URL; fall back to the generated article markdown."""
    if lc.published_url:
        try:
            return await get_content("url", lc.published_url)
        except Exception as exc:
            log.warning("Lifecycle %s: URL fetch failed (%s); using local content", lc.id, exc)
    if job is not None:
        md = _article_to_markdown(job)
        if md.strip():
            return parse_content(md)
    return None


async def _measure_aeo(
    content: ParsedContent, llm: LlmClient
) -> tuple[int | None, str | None, dict]:
    checks = [
        await check_direct_answer(content, llm),
        check_htag_hierarchy(content),
        check_readability(content),
    ]
    score, band = compute_aeo_score(checks)
    return score, band, {"checks": [c.model_dump() for c in checks]}


async def _measure_rank(lc: Lifecycle, serp: SerpProvider) -> int | None:
    """Find the published URL's position in the SERP for the target query."""
    if not lc.published_url:
        return None
    try:
        data = await serp.search(lc.measure_query or lc.topic)
    except Exception as exc:
        log.warning("Lifecycle %s: SERP search failed: %s", lc.id, exc)
        return None
    target_domain = urlparse(lc.published_url).netloc.lower()
    target_url = lc.published_url.rstrip("/").lower()
    for r in data.results:
        if target_url and r.url.rstrip("/").lower() == target_url:
            return r.rank
        if target_domain and target_domain in (r.domain or "").lower():
            return r.rank
    return None


async def _measure_brand(lc: Lifecycle, llm: LlmClient) -> float | None:
    """Best-effort brand visibility via the brand-monitor fetch + analyze pipeline."""
    if not lc.brand_name:
        return None
    try:
        from app.brand.analyzer import analyze_brand
        from app.brand.fetcher import fetch_platform_responses
        from app.brand.models import BrandMonitorRequest

        query = lc.measure_query or lc.topic
        responses = await fetch_platform_responses(query, web_search=False)
        if not responses:
            return None
        for r in responses:
            r.query = query
        req = BrandMonitorRequest(brand_name=lc.brand_name, query=query)
        result = await analyze_brand(req, llm=llm, responses=responses, queries=[query])
        return result.scores.visibility_score if result.scores else None
    except Exception as exc:
        log.warning("Lifecycle %s: brand measurement failed: %s", lc.id, exc)
        return None


async def measure_lifecycle(
    session: AsyncSession,
    lc: Lifecycle,
    *,
    llm: LlmClient,
    serp: SerpProvider,
    now: datetime,
) -> LifecycleMeasurement:
    """Run all measurements, persist a snapshot, and update the lifecycle's latest columns.

    The returned measurement is added to the session but not committed — the caller commits.
    """
    job = await session.get(Job, lc.current_job_id) if lc.current_job_id else None

    content = await _resolve_content(lc, job)
    if content is not None:
        aeo_score, aeo_band, aeo_raw = await _measure_aeo(content, llm)
    else:
        aeo_score, aeo_band, aeo_raw = None, None, {}

    rank = await _measure_rank(lc, serp)
    brand_vis = await _measure_brand(lc, llm)
    ref = ensure_aware(lc.last_refresh_at)
    age = (now - ref).days if ref else None

    measurement = LifecycleMeasurement(
        lifecycle_id=lc.id,
        cycle_count=lc.cycle_count,
        job_id=lc.current_job_id,
        aeo_score=aeo_score,
        aeo_band=aeo_band,
        rank_position=rank,
        brand_visibility=brand_vis,
        content_age_days=age,
        raw_data={"aeo": aeo_raw},
    )
    session.add(measurement)

    # Snapshot latest values onto the lifecycle for fast reads
    lc.last_aeo_score = aeo_score
    lc.last_rank_position = rank
    lc.last_brand_visibility = brand_vis

    return measurement
