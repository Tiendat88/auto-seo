"""SEO Lifecycle API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.lifecycle.models import (
    Lifecycle,
    LifecycleCreateRequest,
    LifecycleListResponse,
    LifecyclePhase,
    LifecycleResponse,
    MeasurementListResponse,
    TickResponse,
    to_response,
    to_summary,
    utcnow,
)
from app.lifecycle.scheduler import dispatch_measurement, spawn_generation, tick
from app.lifecycle.service import (
    advance_lifecycle,
    create_lifecycle,
    force_refresh,
    get_lifecycle,
    list_lifecycles,
    list_measurements,
    set_enabled,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/lifecycles", tags=["lifecycles"])


async def _require(session: AsyncSession, lifecycle_id: str) -> Lifecycle:
    lc = await get_lifecycle(session, lifecycle_id)
    if not lc:
        raise HTTPException(status_code=404, detail="Lifecycle not found")
    return lc


@router.post("", status_code=201, response_model=LifecycleResponse)
async def create_lifecycle_endpoint(
    request: LifecycleCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> LifecycleResponse:
    lc = await create_lifecycle(session, request)
    if request.generate_now:
        await advance_lifecycle(
            session, lc, now=utcnow(),
            spawn=spawn_generation, dispatch_measure=dispatch_measurement,
        )
        await session.refresh(lc)
    log.info("Created lifecycle=%s for topic=%s (cadence=%dd)", lc.id, lc.topic, lc.cadence_days)
    return to_response(lc)


@router.get("", response_model=LifecycleListResponse)
async def list_lifecycles_endpoint(
    phase: LifecyclePhase | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> LifecycleListResponse:
    rows, total = await list_lifecycles(
        session, phase=phase, enabled=enabled, limit=limit, offset=offset
    )
    return LifecycleListResponse(lifecycles=[to_summary(lc) for lc in rows], total=total)


@router.get("/{lifecycle_id}", response_model=LifecycleResponse)
async def get_lifecycle_endpoint(
    lifecycle_id: str,
    session: AsyncSession = Depends(get_session),
) -> LifecycleResponse:
    return to_response(await _require(session, lifecycle_id))


@router.get("/{lifecycle_id}/measurements", response_model=MeasurementListResponse)
async def list_measurements_endpoint(
    lifecycle_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> MeasurementListResponse:
    await _require(session, lifecycle_id)
    rows, total = await list_measurements(session, lifecycle_id, limit=limit)
    return MeasurementListResponse(
        measurements=[m.to_response() for m in rows], total=total
    )


@router.post("/{lifecycle_id}/pause", response_model=LifecycleResponse)
async def pause_lifecycle_endpoint(
    lifecycle_id: str,
    session: AsyncSession = Depends(get_session),
) -> LifecycleResponse:
    lc = await _require(session, lifecycle_id)
    return to_response(await set_enabled(session, lc, False))


@router.post("/{lifecycle_id}/resume", response_model=LifecycleResponse)
async def resume_lifecycle_endpoint(
    lifecycle_id: str,
    session: AsyncSession = Depends(get_session),
) -> LifecycleResponse:
    lc = await _require(session, lifecycle_id)
    return to_response(await set_enabled(session, lc, True))


@router.post("/{lifecycle_id}/refresh", response_model=LifecycleResponse)
async def refresh_lifecycle_endpoint(
    lifecycle_id: str,
    session: AsyncSession = Depends(get_session),
) -> LifecycleResponse:
    lc = await _require(session, lifecycle_id)
    await force_refresh(session, lc)
    await advance_lifecycle(
        session, lc, now=utcnow(),
        spawn=spawn_generation, dispatch_measure=dispatch_measurement,
    )
    await session.refresh(lc)
    return to_response(lc)


@router.post("/{lifecycle_id}/measure", response_model=LifecycleResponse)
async def measure_lifecycle_endpoint(
    lifecycle_id: str,
    session: AsyncSession = Depends(get_session),
) -> LifecycleResponse:
    lc = await _require(session, lifecycle_id)
    lc.phase = LifecyclePhase.MEASURING
    await session.commit()
    await session.refresh(lc)
    dispatch_measurement(lc.id)
    return to_response(lc)


@router.post("/tick", response_model=TickResponse)
async def tick_endpoint(
    session: AsyncSession = Depends(get_session),
) -> TickResponse:
    """Run a single scheduler tick. Debug/ops hook — gated behind DEBUG."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    advanced = await tick(session, now=utcnow())
    return TickResponse(advanced=advanced)
