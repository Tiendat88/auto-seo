"""Lifecycle orchestration: CRUD, the phase state machine, and measurement completion.

The heavy work (running the pipeline, calling LLMs to measure) is never run inline here —
``advance_lifecycle`` only does fast DB work and hands blocking work to injected ``spawn`` /
``dispatch_measure`` callbacks (provided by the scheduler in production).
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.job.models import ArticleRequest, Job, JobStatus
from app.job.service import create_job
from app.lifecycle.measure import decide_refresh, measure_lifecycle
from app.lifecycle.models import (
    Lifecycle,
    LifecycleCreateRequest,
    LifecycleMeasurement,
    LifecyclePhase,
    ensure_aware,
    utcnow,
)
from app.llm import LlmClient
from app.publish.models import PublishJob
from app.serp.client import SerpProvider

log = logging.getLogger(__name__)

# Injected background dispatch callbacks (see app/lifecycle/scheduler.py).
SpawnFn = Callable[[str, str], None]      # (job_id, lifecycle_id)
DispatchMeasureFn = Callable[[str], None]  # (lifecycle_id)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_lifecycle(
    session: AsyncSession, request: LifecycleCreateRequest
) -> Lifecycle:
    lc = Lifecycle(
        topic=request.topic,
        target_word_count=request.target_word_count,
        language=request.language,
        webhook_url=request.webhook_url,
        cadence_days=request.cadence_days,
        measure_query=request.measure_query,
        brand_name=request.brand_name,
        phase=LifecyclePhase.CREATED,
        next_run_at=utcnow(),
    )
    if request.brand_voice:
        lc.set_brand_voice(request.brand_voice)
    if request.policy:
        lc.set_policy(request.policy)
    session.add(lc)
    await session.commit()
    await session.refresh(lc)
    return lc


async def get_lifecycle(session: AsyncSession, lifecycle_id: str) -> Lifecycle | None:
    return await session.get(Lifecycle, lifecycle_id)


async def list_lifecycles(
    session: AsyncSession,
    phase: LifecyclePhase | None = None,
    enabled: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Lifecycle], int]:
    query = select(Lifecycle)
    count_query = select(func.count()).select_from(Lifecycle)
    if phase is not None:
        query = query.where(Lifecycle.phase == phase)
        count_query = count_query.where(Lifecycle.phase == phase)
    if enabled is not None:
        query = query.where(Lifecycle.enabled.is_(enabled))
        count_query = count_query.where(Lifecycle.enabled.is_(enabled))
    query = query.order_by(Lifecycle.created_at.desc()).offset(offset).limit(limit)

    rows = list((await session.execute(query)).scalars().all())
    total = (await session.execute(count_query)).scalar_one()
    return rows, total


async def list_measurements(
    session: AsyncSession, lifecycle_id: str, limit: int = 50
) -> tuple[list[LifecycleMeasurement], int]:
    query = (
        select(LifecycleMeasurement)
        .where(LifecycleMeasurement.lifecycle_id == lifecycle_id)
        .order_by(LifecycleMeasurement.created_at.desc())
        .limit(limit)
    )
    count_query = (
        select(func.count())
        .select_from(LifecycleMeasurement)
        .where(LifecycleMeasurement.lifecycle_id == lifecycle_id)
    )
    rows = list((await session.execute(query)).scalars().all())
    total = (await session.execute(count_query)).scalar_one()
    return rows, total


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


async def _spawn_generation(
    session: AsyncSession, lc: Lifecycle, now: datetime, spawn: SpawnFn
) -> None:
    """Create a fresh Job (generate or refresh — identical) and dispatch it in the background."""
    req = ArticleRequest(
        topic=lc.topic,
        target_word_count=lc.target_word_count,
        language=lc.language,
        brand_voice=lc.get_brand_voice(),
        webhook_url=lc.webhook_url,
    )
    job = await create_job(session, req)
    lc.current_job_id = job.id
    lc.append_cycle_job(job.id)
    lc.phase = LifecyclePhase.GENERATING
    lc.last_run_at = now
    lc.error = None
    await session.commit()
    spawn(job.id, lc.id)


async def _latest_published_url(session: AsyncSession, job_id: str) -> str | None:
    result = await session.execute(
        select(PublishJob.published_url)
        .where(PublishJob.job_id == job_id, PublishJob.published_url.is_not(None))
        .order_by(PublishJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def handle_generation_complete(
    session: AsyncSession, lc: Lifecycle, now: datetime
) -> None:
    """GENERATING → DONE / MONITORING / FAILED based on the current Job's terminal status.

    Idempotent: safe to call from both the job-completion callback and a scheduler poll.
    """
    if not lc.current_job_id:
        return
    job = await session.get(Job, lc.current_job_id)
    if job is None:
        lc.phase = LifecyclePhase.FAILED
        lc.error = "Generation job missing"
        await session.commit()
        return

    status = JobStatus(job.status)
    if status == JobStatus.COMPLETED:
        url = await _latest_published_url(session, job.id)
        if url:
            lc.published_url = url
        lc.last_refresh_at = now
        lc.error = None
        if lc.cadence_days and lc.cadence_days > 0:
            lc.phase = LifecyclePhase.MONITORING
            lc.next_run_at = now + timedelta(days=lc.cadence_days)
        else:
            lc.phase = LifecyclePhase.DONE
            lc.next_run_at = None
        await session.commit()
    elif status == JobStatus.FAILED:
        lc.phase = LifecyclePhase.FAILED
        lc.error = f"Generation job {job.id} failed: {job.error or 'unknown'}"
        await session.commit()
    # else: still running → no-op


async def advance_lifecycle(
    session: AsyncSession,
    lc: Lifecycle,
    *,
    now: datetime,
    spawn: SpawnFn,
    dispatch_measure: DispatchMeasureFn,
) -> None:
    """Advance a lifecycle by exactly one phase transition. Fast DB work only."""
    phase = LifecyclePhase(lc.phase)

    if phase in (LifecyclePhase.CREATED, LifecyclePhase.NEEDS_REFRESH):
        await _spawn_generation(session, lc, now, spawn)
    elif phase == LifecyclePhase.GENERATING:
        await handle_generation_complete(session, lc, now)
    elif phase == LifecyclePhase.MONITORING:
        next_run = ensure_aware(lc.next_run_at)
        if next_run is None or now >= next_run:
            lc.phase = LifecyclePhase.MEASURING
            await session.commit()
            dispatch_measure(lc.id)
    # PAUSED / MEASURING / DONE / FAILED → no-op


async def complete_measurement(
    session: AsyncSession,
    lc: Lifecycle,
    *,
    llm: LlmClient,
    serp: SerpProvider,
    now: datetime,
) -> LifecycleMeasurement:
    """MEASURING work: measure all signals, decide refresh, transition the lifecycle."""
    measurement = await measure_lifecycle(session, lc, llm=llm, serp=serp, now=now)
    policy = lc.get_policy()
    decayed, reasons = decide_refresh(
        rank=measurement.rank_position,
        aeo=measurement.aeo_score,
        brand=measurement.brand_visibility,
        age_days=measurement.content_age_days,
        policy=policy,
    )
    measurement.decayed = decayed
    measurement.decay_reasons = reasons
    lc.last_run_at = now
    if decayed:
        lc.phase = LifecyclePhase.NEEDS_REFRESH
        lc.next_run_at = now
    else:
        lc.phase = LifecyclePhase.MONITORING
        lc.next_run_at = now + timedelta(days=max(lc.cadence_days, 1))
    await session.commit()
    return measurement


async def on_job_finished(lifecycle_id: str, job_id: str) -> None:
    """Callback invoked by ``run_job_background`` once a lifecycle-owned Job settles."""
    async with async_session() as session:
        lc = await session.get(Lifecycle, lifecycle_id)
        if lc is None or lc.current_job_id != job_id:
            return
        if LifecyclePhase(lc.phase) != LifecyclePhase.GENERATING:
            return
        await handle_generation_complete(session, lc, utcnow())


# ---------------------------------------------------------------------------
# Manual operations (CLI/API)
# ---------------------------------------------------------------------------


async def set_enabled(session: AsyncSession, lc: Lifecycle, enabled: bool) -> Lifecycle:
    lc.enabled = enabled
    if enabled and LifecyclePhase(lc.phase) == LifecyclePhase.PAUSED:
        lc.phase = LifecyclePhase.MONITORING
        lc.next_run_at = utcnow()
    elif not enabled:
        lc.phase = LifecyclePhase.PAUSED
    await session.commit()
    await session.refresh(lc)  # reload server-side updated_at to avoid MissingGreenlet
    return lc


async def force_refresh(session: AsyncSession, lc: Lifecycle) -> Lifecycle:
    lc.phase = LifecyclePhase.NEEDS_REFRESH
    lc.enabled = True
    lc.next_run_at = utcnow()
    await session.commit()
    await session.refresh(lc)
    return lc
