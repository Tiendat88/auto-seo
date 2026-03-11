"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cache import cache
from app.db import init_db
from app.job.routes import router as jobs_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await cache.connect()
    yield
    # Running pipeline tasks are not cancelled on shutdown.
    # Jobs left in intermediate state can be resumed via POST /jobs/{id}/resume.
    await cache.close()


app = FastAPI(
    title="SEO Article Generator",
    description="Backend service for generating SEO-optimized articles",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(jobs_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
