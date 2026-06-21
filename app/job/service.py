"""Job CRUD operations and the background pipeline runner."""

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.article.pipeline import run_pipeline
from app.db import async_session
from app.job.models import ArticleRequest, Job, JobStatus
from app.llm import LlmClient
from app.serp.client import get_serp_provider

log = logging.getLogger(__name__)


async def create_job(session: AsyncSession, request: ArticleRequest) -> Job:
    job = Job(
        topic=request.topic,
        target_word_count=request.target_word_count,
        language=request.language,
        webhook_url=request.webhook_url,
    )
    if request.brand_voice:
        job.set_brand_voice(request.brand_voice)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, job_id: str) -> Job | None:
    return await session.get(Job, job_id)


async def list_jobs(
    session: AsyncSession,
    status: JobStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Job], int]:
    query = select(Job)
    count_query = select(func.count()).select_from(Job)

    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)

    query = query.order_by(Job.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    jobs = list(result.scalars().all())

    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    return jobs, total


async def claim_job_for_resume(
    session: AsyncSession, job_id: str
) -> Job | None:
    """Atomically claim a job for resume. Returns the job if claimed, None if already running."""
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .where(Job.status == JobStatus.FAILED)
        .values(status=JobStatus.PENDING, error=None)
        .returning(Job.id)
    )
    claimed = result.scalar_one_or_none()
    await session.commit()
    if not claimed:
        return None
    job = await session.get(Job, job_id)
    if job:
        await session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Background pipeline runner (shared by the job route and the SEO lifecycle)
# ---------------------------------------------------------------------------


async def _auto_post_webhook(job: Job) -> None:
    """POST the completed article to the job's custom webhook, if configured."""
    if not job.webhook_url:
        return
    try:
        import httpx

        payload = {
            "topic": job.topic,
            "article_data": job.article_data,
            "seo_metadata": job.seo_metadata_data,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(job.webhook_url, json=payload, timeout=10.0)
            if resp.status_code >= 400:
                log.warning("Webhook failed with status %s: %s", resp.status_code, resp.text)
            else:
                log.info("Auto-posted to custom webhook: %s", job.webhook_url)
    except Exception as exc:
        log.error("Failed to auto-post: %s", exc)


async def _auto_publish(session: AsyncSession, job: Job) -> None:
    """Publish the completed article to every target flagged auto_publish=True."""
    try:
        from app.publish.models import (
            PublishJob,
            PublishJobStatus,
            PublishMode,
            PublishTarget,
        )
        from app.publish.service import publish_article

        auto_targets = (
            await session.execute(
                select(PublishTarget).where(PublishTarget.auto_publish.is_(True))
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
    except Exception as exc:
        log.error("Auto-publish failed for job %s: %s", job.id, exc)


async def run_job_background(job_id: str, lifecycle_id: str | None = None) -> None:
    """Run the pipeline in the background with its own session, then auto-post / auto-publish.

    When ``lifecycle_id`` is set, notify the owning lifecycle once the job settles so it can
    advance (capture published_url, schedule the next measurement, or mark itself failed).
    """
    try:
        llm = LlmClient()
        serp = get_serp_provider()
        async with async_session() as session:
            await run_pipeline(job_id, session, llm, serp)

            job = await session.get(Job, job_id)
            if job and job.status == JobStatus.COMPLETED:
                log.info("Job %s completed successfully", job_id)
                await _auto_post_webhook(job)
                await _auto_publish(session, job)
    except Exception as exc:
        log.exception("Pipeline background task failed for job=%s", job_id)
        try:
            async with async_session() as session:
                job = await session.get(Job, job_id)
                if job and job.status != JobStatus.COMPLETED:
                    job.status = JobStatus.FAILED
                    job.error = f"Pipeline startup failed: {type(exc).__name__}"
                    session.add(job)
                    await session.commit()
        except Exception:
            log.exception("Failed to mark job=%s as failed", job_id)
    finally:
        if lifecycle_id:
            try:
                from app.lifecycle.service import on_job_finished

                await on_job_finished(lifecycle_id, job_id)
            except Exception:
                log.exception(
                    "Failed to notify lifecycle=%s after job=%s", lifecycle_id, job_id
                )
