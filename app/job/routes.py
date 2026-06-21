"""Job API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.article.pipeline import run_pipeline
from app.db import async_session, get_session
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
from app.job.service import claim_job_for_resume, create_job, get_job, list_jobs
from app.llm import LlmClient
from app.serp.client import get_serp_provider

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


async def _run_pipeline_background(job_id: str) -> None:
    """Run pipeline in background with its own session."""
    try:
        llm = LlmClient()
        serp = get_serp_provider()
        async with async_session() as session:
            await run_pipeline(job_id, session, llm, serp)

            # --- AUTO POST TO OPENCLAW WORKSPACE ---
            job = await session.get(Job, job_id)
            if job and job.status == JobStatus.COMPLETED:
                log.info("Job %s completed successfully", job_id)
                try:
                    import httpx

                    from app.config import settings

                    # Post to Custom Webhook (if configured)
                    if job.webhook_url:
                        payload = {
                            "topic": job.topic,
                            "article_data": job.article_data,
                            "seo_metadata": job.seo_metadata_data,
                        }
                        # Fire and forget POST request
                        async with httpx.AsyncClient() as client:
                            resp = await client.post(
                                job.webhook_url, json=payload, timeout=10.0
                            )
                            if resp.status_code >= 400:
                                log.warning(
                                    "Webhook failed with status %s: %s",
                                    resp.status_code, resp.text,
                                )
                            else:
                                log.info("Auto-posted to custom webhook: %s", job.webhook_url)
                except Exception as e:
                    log.error("Failed to auto-post: %s", e)

                # --- AUTO-PUBLISH to targets flagged auto_publish ---
                try:
                    from sqlalchemy import select as _select

                    from app.publish.models import (
                        PublishJob,
                        PublishJobStatus,
                        PublishMode,
                        PublishTarget,
                    )
                    from app.publish.service import publish_article

                    auto_targets = (
                        await session.execute(
                            _select(PublishTarget).where(PublishTarget.auto_publish.is_(True))
                        )
                    ).scalars().all()

                    for target in auto_targets:
                        publish_job = PublishJob(
                            job_id=job.id,
                            target_id=target.id,
                            target_name=target.name,
                            target_url=target.endpoint_url,
                            mode=PublishMode(target.default_mode),
                            status=PublishJobStatus.PENDING,
                        )
                        session.add(publish_job)
                        await session.commit()
                        await session.refresh(publish_job)
                        await publish_article(session, publish_job, target, job)
                        log.info(
                            "Auto-published job %s to target '%s' (status=%s)",
                            job.id, target.name, publish_job.status,
                        )
                except Exception as e:
                    log.error("Auto-publish failed for job %s: %s", job_id, e)

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


@router.post("", status_code=201, response_model=JobResponse)
async def create_job_endpoint(
    request: ArticleRequest,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await create_job(session, request)
    _track_task(asyncio.create_task(_run_pipeline_background(job.id)))
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
        _track_task(asyncio.create_task(_run_pipeline_background(job.id)))
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

    _track_task(asyncio.create_task(_run_pipeline_background(job.id)))
    log.info("Resumed job=%s", job.id)
    return _job_to_response(job)
