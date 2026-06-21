"""Job API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.job.models import (
    ArticleRequest,
    CampaignRequest,
    CampaignResponse,
    Job,
    JobListResponse,
    JobResponse,
    JobStatus,
    JobSummaryResponse,
    KeywordCluster,
)
from app.job.service import (
    claim_job_for_resume,
    create_job,
    get_job,
    list_jobs,
    run_job_background,
)
from app.llm import LlmClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])

# Prevent GC from silently killing running pipeline tasks
_running_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> None:
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)


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
        webhook_url=job.webhook_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _job_to_response(job: Job, full: bool = False) -> JobResponse:
    done = job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
    result = job.build_result() if job.status == JobStatus.COMPLETED else None
    # Skip heavy artifact deserialization for in-progress polls
    include_artifacts = done or full
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
        serp_data=job.get_serp() if include_artifacts else None,
        analysis_data=job.get_analysis() if include_artifacts else None,
        outline_data=job.get_outline() if include_artifacts else None,
        article_data=job.get_article() if include_artifacts else None,
        quality_data=job.get_quality() if include_artifacts else None,
        review_data=job.get_review() if include_artifacts else None,
        usage_data=job.usage_data if include_artifacts else None,
        events_data=job.events_data,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", status_code=201, response_model=JobResponse)
async def create_job_endpoint(
    request: ArticleRequest,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await create_job(session, request)
    _track_task(asyncio.create_task(run_job_background(job.id)))
    log.info("Created job=%s for topic=%s", job.id, job.topic)
    return _job_to_response(job)


@router.post("/campaign", status_code=201, response_model=CampaignResponse)
async def create_campaign_endpoint(
    request: CampaignRequest,
    session: AsyncSession = Depends(get_session),
) -> CampaignResponse:
    llm = LlmClient()
    prompt = (
        f"Generate {request.num_keywords} highly relevant, long-tail sub-keywords "
        f"or article topics for the main keyword: '{request.main_keyword}'. "
        f"Language: {request.language}. Ensure they have good search intent."
    )
    cluster = await llm.generate_structured(prompt, KeywordCluster)

    created_jobs = []
    for kw in cluster.keywords:
        job_req = ArticleRequest(
            topic=kw,
            target_word_count=request.target_word_count,
            language=request.language,
            brand_voice=request.brand_voice,
            webhook_url=request.webhook_url,
        )
        job = await create_job(session, job_req)
        _track_task(asyncio.create_task(run_job_background(job.id)))
        created_jobs.append(_job_to_summary(job))
        log.info("Created campaign job=%s for topic=%s", job.id, job.topic)

    return CampaignResponse(
        main_keyword=request.main_keyword,
        generated_keywords=cluster.keywords,
        jobs=created_jobs
    )


@router.get("", response_model=JobListResponse)
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
    full: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job, full=full)


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

    _track_task(asyncio.create_task(run_job_background(job.id)))
    log.info("Resumed job=%s", job.id)
    return _job_to_response(job)
