"""Job CRUD operations."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.job.models import ArticleRequest, Job, JobStatus


async def create_job(session: AsyncSession, request: ArticleRequest) -> Job:
    job = Job(
        topic=request.topic,
        target_word_count=request.target_word_count,
        language=request.language,
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
        .where(
            Job.status.in_([
                JobStatus.FAILED,
                JobStatus.PENDING,
            ])
        )
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
