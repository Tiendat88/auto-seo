"""Lifecycle scheduler: leader election, due-poll loop, and background dispatch.

Designed for ``uvicorn --workers 2``: only the worker that wins a Postgres advisory lock
runs the poll loop, so lifecycles never double-fire. The leader loop does only fast DB work
and hands all event-loop-blocking work (pipeline runs, LLM measurement) to tracked
background tasks — mirroring the existing job-route pattern.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session, engine, try_acquire_scheduler_lock
from app.job.service import run_job_background
from app.lifecycle.models import ACTIVE_PHASES, Lifecycle, LifecyclePhase
from app.lifecycle.service import (
    advance_lifecycle,
    complete_measurement,
)
from app.llm import LlmClient
from app.serp.client import get_serp_provider

log = logging.getLogger(__name__)

# Prevent GC from killing in-flight dispatched tasks.
_running_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> None:
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Background dispatch callbacks (injected into advance_lifecycle)
# ---------------------------------------------------------------------------


def spawn_generation(job_id: str, lifecycle_id: str) -> None:
    """Fire-and-forget: run the pipeline for a lifecycle-owned Job."""
    _track_task(asyncio.create_task(run_job_background(job_id, lifecycle_id)))


def dispatch_measurement(lifecycle_id: str) -> None:
    """Fire-and-forget: run a measurement pass for a lifecycle."""
    _track_task(asyncio.create_task(run_measurement_background(lifecycle_id)))


async def run_measurement_background(lifecycle_id: str) -> None:
    """Measure a lifecycle in its own session; revert to MONITORING on failure."""
    try:
        llm = LlmClient()
        serp = get_serp_provider()
        async with async_session() as session:
            lc = await session.get(Lifecycle, lifecycle_id)
            if lc is None or LifecyclePhase(lc.phase) != LifecyclePhase.MEASURING:
                return
            await complete_measurement(session, lc, llm=llm, serp=serp, now=_utcnow())
    except Exception:
        log.exception("Measurement failed for lifecycle=%s", lifecycle_id)
        try:
            async with async_session() as session:
                lc = await session.get(Lifecycle, lifecycle_id)
                if lc and LifecyclePhase(lc.phase) == LifecyclePhase.MEASURING:
                    lc.phase = LifecyclePhase.MONITORING
                    lc.next_run_at = _utcnow()
                    await session.commit()
        except Exception:
            log.exception("Failed to revert MEASURING lifecycle=%s", lifecycle_id)


# ---------------------------------------------------------------------------
# Tick + leader loop
# ---------------------------------------------------------------------------


async def tick(
    session: AsyncSession,
    *,
    now: datetime,
    spawn=spawn_generation,
    dispatch_measure=dispatch_measurement,
) -> list[str]:
    """Advance every due, enabled lifecycle by one phase. The test seam — no sleeping."""
    in_flight = (
        await session.execute(
            select(func.count())
            .select_from(Lifecycle)
            .where(Lifecycle.phase == LifecyclePhase.GENERATING)
        )
    ).scalar_one()

    due = list(
        (
            await session.execute(
                select(Lifecycle)
                .where(
                    Lifecycle.enabled.is_(True),
                    Lifecycle.phase.in_(list(ACTIVE_PHASES)),
                    or_(Lifecycle.next_run_at.is_(None), Lifecycle.next_run_at <= now),
                )
                .order_by(Lifecycle.created_at.asc())
                .limit(settings.lifecycle_batch_size)
            )
        ).scalars().all()
    )

    cap = settings.lifecycle_max_concurrent
    advanced: list[str] = []
    for lc in due:
        phase = LifecyclePhase(lc.phase)
        if phase in (LifecyclePhase.CREATED, LifecyclePhase.NEEDS_REFRESH):
            if in_flight >= cap:
                continue  # defer spawn; re-picked on a later tick
            in_flight += 1
        await advance_lifecycle(
            session, lc, now=now, spawn=spawn, dispatch_measure=dispatch_measure
        )
        advanced.append(lc.id)
    return advanced


async def run_scheduler_loop() -> None:
    """Leader-elected poll loop. Started from the app lifespan when lifecycle_enabled."""
    interval = settings.lifecycle_poll_interval_seconds
    while True:
        try:
            async with engine.connect() as conn:
                if not await try_acquire_scheduler_lock(conn):
                    await asyncio.sleep(interval)
                    continue
                log.info("Lifecycle scheduler: leadership acquired")
                while True:
                    try:
                        async with async_session() as session:
                            advanced = await tick(session, now=_utcnow())
                        if advanced:
                            log.info(
                                "Lifecycle tick advanced %d lifecycle(s)", len(advanced)
                            )
                    except Exception:
                        log.exception("Lifecycle tick failed")
                    await asyncio.sleep(interval)
        except asyncio.CancelledError:
            log.info("Lifecycle scheduler: stopping")
            raise
        except Exception:
            log.exception("Lifecycle scheduler loop error; retrying in %ss", interval)
            await asyncio.sleep(interval)


async def recover_orphaned_lifecycles() -> None:
    """On startup: re-arm lifecycles stuck mid-flight by a server restart.

    GENERATING/MEASURING lifecycles whose work was interrupted are flipped back to a
    re-drivable state (MONITORING due now), mirroring the job orphan-recovery policy.
    """
    from sqlalchemy import update

    async with async_session() as session:
        result = await session.execute(
            update(Lifecycle)
            .where(Lifecycle.phase.in_([LifecyclePhase.MEASURING, LifecyclePhase.GENERATING]))
            .values(phase=LifecyclePhase.MONITORING, next_run_at=_utcnow())
            .returning(Lifecycle.id)
        )
        recovered = list(result.scalars().all())
        await session.commit()
        if recovered:
            log.info("Re-armed %d orphaned lifecycle(s): %s", len(recovered), recovered)
