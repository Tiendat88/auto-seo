"""Job API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.article.pipeline import run_pipeline
from app.db import async_session, get_session
from app.job.models import (
    ArticleRequest,
    Job,
    JobListResponse,
    JobResponse,
    JobStatus,
    JobSummaryResponse,
)
from app.job.service import claim_job_for_resume, create_job, get_job, list_jobs
from app.llm import LlmClient
from app.serp.client import get_serp_provider

log = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_to_summary(job: Job) -> JobSummaryResponse:
    return JobSummaryResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        topic=job.topic,
        target_word_count=job.target_word_count,
        language=job.language,
        current_step=job.current_step,
        error=job.error,
        revision_count=job.revision_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _job_to_response(job: Job) -> JobResponse:
    result = job.build_result() if job.status == JobStatus.COMPLETED else None
    return JobResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        topic=job.topic,
        target_word_count=job.target_word_count,
        language=job.language,
        current_step=job.current_step,
        error=job.error,
        revision_count=job.revision_count,
        result=result,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


async def _run_pipeline_background(job_id: str) -> None:
    """Run pipeline in background with its own session."""
    try:
        llm = LlmClient()
        serp = get_serp_provider()
        async with async_session() as session:
            await run_pipeline(job_id, session, llm, serp)
    except Exception as e:
        log.exception("Pipeline background task failed for job=%s", job_id)
        try:
            async with async_session() as session:
                job = await session.get(Job, job_id)
                if job and job.status != JobStatus.COMPLETED:
                    job.status = JobStatus.FAILED
                    job.error = f"Pipeline startup failed: {type(e).__name__}"
                    session.add(job)
                    await session.commit()
        except Exception:
            log.exception("Failed to mark job=%s as failed", job_id)


@router.post("/", status_code=201, response_model=JobResponse)
async def create_job_endpoint(
    request: ArticleRequest,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await create_job(session, request)
    asyncio.create_task(_run_pipeline_background(job.id))
    log.info("Created job=%s for topic=%s", job.id, job.topic)
    return _job_to_response(job)


@router.get("/", response_model=JobListResponse)
async def list_jobs_endpoint(
    status: JobStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> JobListResponse:
    jobs, total = await list_jobs(session, status=status, limit=limit, offset=offset)
    return JobListResponse(
        jobs=[_job_to_summary(j) for j in jobs],
        total=total,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_endpoint(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.post("/{job_id}/resume", response_model=JobResponse)
async def resume_job_endpoint(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job already completed")

    job = await claim_job_for_resume(session, job_id)
    if not job:
        raise HTTPException(
            status_code=409, detail="Job could not be claimed for resume"
        )

    asyncio.create_task(_run_pipeline_background(job.id))
    log.info("Resumed job=%s", job.id)
    return _job_to_response(job)
