"""FastAPI routes for the publish module."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.job.models import Job, JobStatus
from app.publish.models import PublishJob, PublishJobStatus, PublishMode, PublishTarget
from app.publish.service import publish_article, test_target_connection

log = logging.getLogger(__name__)
router = APIRouter(prefix="/publish", tags=["publish"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateTargetRequest(BaseModel):
    name: str
    endpoint_url: str
    secret_key: str
    default_mode: PublishMode = PublishMode.DRAFT
    auto_publish: bool = False


class CreatePublishJobRequest(BaseModel):
    job_id: str
    target_id: str
    mode: PublishMode | None = None   # overrides target default if set


class TestConnectionRequest(BaseModel):
    endpoint_url: str
    secret_key: str


# ---------------------------------------------------------------------------
# Publish Targets CRUD
# ---------------------------------------------------------------------------


@router.post("/targets", status_code=201)
async def create_target(
    body: CreateTargetRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    target = PublishTarget(
        name=body.name,
        endpoint_url=str(body.endpoint_url),
        secret_key=body.secret_key,
        default_mode=body.default_mode,
        auto_publish=body.auto_publish,
    )
    session.add(target)
    await session.commit()
    await session.refresh(target)
    return target.to_dict()


@router.get("/targets")
async def list_targets(
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(PublishTarget).order_by(PublishTarget.created_at.desc()))
    targets = result.scalars().all()
    return {"targets": [t.to_dict() for t in targets], "total": len(targets)}


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(
    target_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    target = await session.get(PublishTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    await session.delete(target)
    await session.commit()


@router.post("/targets/test")
async def test_connection(body: TestConnectionRequest) -> dict:
    """Send a test ping to the endpoint and return the result."""
    try:
        result = await test_target_connection(str(body.endpoint_url), body.secret_key)
        return {"success": True, "response": result}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Publish Jobs
# ---------------------------------------------------------------------------


async def _run_publish(publish_job_id: str, target_id: str, job_id: str) -> None:
    """Background task: load records fresh, run publish, commit."""
    from app.db import async_session  # avoid circular import at module level

    async with async_session() as session:
        publish_job = await session.get(PublishJob, publish_job_id)
        target = await session.get(PublishTarget, target_id)
        job = await session.get(Job, job_id)

        if not publish_job or not target or not job:
            log.error("Publish background task: missing record(s)")
            return

        await publish_article(session, publish_job, target, job)


@router.post("/jobs", status_code=201)
async def create_publish_job(
    body: CreatePublishJobRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Validate target exists
    target = await session.get(PublishTarget, body.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Publish target not found")

    # Validate article job exists and is completed
    job = await session.get(Job, body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Article job is not completed (current status: {job.status})"
        )

    mode = body.mode or PublishMode(target.default_mode)

    publish_job = PublishJob(
        job_id=body.job_id,
        target_id=body.target_id,
        target_name=target.name,
        target_url=target.endpoint_url,
        mode=mode,
        status=PublishJobStatus.PENDING,
    )
    session.add(publish_job)
    await session.commit()
    await session.refresh(publish_job)

    # Fire-and-forget publish in background
    background_tasks.add_task(
        _run_publish, publish_job.id, target.id, job.id
    )

    return publish_job.to_dict()


@router.get("/jobs")
async def list_publish_jobs(
    limit: int = 30,
    offset: int = 0,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    query = select(PublishJob)
    count_query = select(func.count()).select_from(PublishJob)

    if status:
        try:
            status_enum = PublishJobStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        query = query.where(PublishJob.status == status_enum)
        count_query = count_query.where(PublishJob.status == status_enum)

    query = query.order_by(PublishJob.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    jobs = result.scalars().all()
    total = (await session.execute(count_query)).scalar_one()

    return {"jobs": [j.to_dict() for j in jobs], "total": total}


@router.get("/jobs/{publish_job_id}")
async def get_publish_job(
    publish_job_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    pj = await session.get(PublishJob, publish_job_id)
    if not pj:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return pj.to_dict()


@router.post("/jobs/{publish_job_id}/cancel", status_code=200)
async def cancel_publish_job(
    publish_job_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    pj = await session.get(PublishJob, publish_job_id)
    if not pj:
        raise HTTPException(status_code=404, detail="Publish job not found")
    if pj.status not in (PublishJobStatus.PENDING,):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{pj.status}'"
        )
    pj.status = PublishJobStatus.CANCELLED
    await session.commit()
    await session.refresh(pj)
    return pj.to_dict()
