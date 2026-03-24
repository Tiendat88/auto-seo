"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import update

from app.aeo.routes import router as aeo_router
from app.brand.routes import router as brand_router
from app.cache import cache
from app.db import async_session, init_db
from app.job.models import Job, JobStatus
from app.job.routes import router as jobs_router

log = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_ACTIVE_STATUSES = (
    JobStatus.RESEARCHING, JobStatus.PLANNING, JobStatus.GENERATING,
    JobStatus.SCORING, JobStatus.REVIEWING, JobStatus.EDITING,
)


async def _recover_orphaned_jobs() -> None:
    """Mark jobs left in active states as FAILED so they can be resumed."""
    async with async_session() as session:
        result = await session.execute(
            update(Job)
            .where(Job.status.in_(_ACTIVE_STATUSES))
            .values(status=JobStatus.FAILED, error="Recovered: server restarted mid-pipeline")
            .returning(Job.id)
        )
        recovered = result.scalars().all()
        await session.commit()
        if recovered:
            log.info("Recovered %d orphaned job(s): %s", len(recovered), recovered)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await cache.connect()
    await _recover_orphaned_jobs()
    yield
    await cache.close()


app = FastAPI(
    title="SEO Article Generator",
    description="Backend service for generating SEO-optimized articles",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(jobs_router, prefix="/api")
app.include_router(brand_router, prefix="/api")
app.include_router(aeo_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
