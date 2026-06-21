"""Tests for API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.aeo.models import SubQuery, SubQueryType
from app.db import Base, get_session
from app.errors import LlmError
from app.job.models import Job, JobStatus
from app.main import app


@pytest.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture
async def client(test_session_factory):
    async def override_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    # Patch the pipeline to not actually run
    with patch("app.job.routes.run_job_background", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


class TestCreateJob:
    async def test_create_job_returns_201(self, client):
        resp = await client.post("/api/jobs/", json={"topic": "best python frameworks"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["topic"] == "best python frameworks"
        assert "job_id" in data

    async def test_create_job_with_custom_params(self, client):
        resp = await client.post(
            "/api/jobs/",
            json={"topic": "testing topic", "target_word_count": 2000, "language": "es"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["target_word_count"] == 2000
        assert data["language"] == "es"

    async def test_create_job_validates_topic_length(self, client):
        resp = await client.post("/api/jobs/", json={"topic": "ab"})
        assert resp.status_code == 422

    async def test_create_job_validates_word_count(self, client):
        resp = await client.post(
            "/api/jobs/", json={"topic": "valid topic", "target_word_count": 50}
        )
        assert resp.status_code == 422


class TestGetJob:
    async def test_get_existing_job(self, client):
        create_resp = await client.post("/api/jobs/", json={"topic": "test topic here"})
        job_id = create_resp.json()["job_id"]

        resp = await client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id

    async def test_get_nonexistent_job(self, client):
        resp = await client.get("/api/jobs/nonexistent-id")
        assert resp.status_code == 404


class TestListJobs:
    async def test_list_empty(self, client):
        resp = await client.get("/api/jobs/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    async def test_list_with_jobs(self, client):
        await client.post("/api/jobs/", json={"topic": "topic one for test"})
        await client.post("/api/jobs/", json={"topic": "topic two for test"})

        resp = await client.get("/api/jobs/")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["jobs"]) == 2


class TestIntermediateData:
    async def test_new_job_has_null_intermediate_fields(self, client):
        resp = await client.post("/api/jobs/", json={"topic": "intermediate test topic"})
        data = resp.json()
        assert data["serp_data"] is None
        assert data["analysis_data"] is None
        assert data["outline_data"] is None
        assert data["article_data"] is None
        assert data["quality_data"] is None
        assert data["review_data"] is None

    async def test_intermediate_fields_populated_after_step(self, client, test_session_factory):
        create_resp = await client.post("/api/jobs/", json={"topic": "data visibility test"})
        job_id = create_resp.json()["job_id"]

        # Manually inject serp_data onto the job
        async with test_session_factory() as session:
            job = await session.get(Job, job_id)
            job.status = JobStatus.PLANNING
            job.serp_data = {
                "query": "test",
                "results": [
                    {"rank": 1, "url": "https://example.com", "title": "Test", "snippet": "s"}
                ],
                "questions": [],
            }
            session.add(job)
            await session.commit()

        # Default response omits intermediate artifacts for in-progress jobs
        resp = await client.get(f"/api/jobs/{job_id}")
        data = resp.json()
        assert data["serp_data"] is None

        # With ?full=true, intermediate artifacts are included
        resp = await client.get(f"/api/jobs/{job_id}?full=true")
        data = resp.json()
        assert data["serp_data"] is not None
        assert data["serp_data"]["query"] == "test"
        assert data["analysis_data"] is None


class TestResumeJob:
    async def test_resume_nonexistent(self, client):
        resp = await client.post("/api/jobs/fake-id/resume")
        assert resp.status_code == 404

    async def test_resume_completed_job_fails(self, client, test_session_factory):
        create_resp = await client.post("/api/jobs/", json={"topic": "completed topic test"})
        job_id = create_resp.json()["job_id"]

        # Manually set status to completed
        async with test_session_factory() as session:
            job = await session.get(Job, job_id)
            job.status = JobStatus.COMPLETED
            session.add(job)
            await session.commit()

        resp = await client.post(f"/api/jobs/{job_id}/resume")
        assert resp.status_code == 400

    async def test_resume_running_job_fails(self, client, test_session_factory):
        create_resp = await client.post("/api/jobs/", json={"topic": "running topic test"})
        job_id = create_resp.json()["job_id"]

        # Manually set status to RESEARCHING (actively running)
        async with test_session_factory() as session:
            job = await session.get(Job, job_id)
            job.status = JobStatus.RESEARCHING
            session.add(job)
            await session.commit()

        resp = await client.post(f"/api/jobs/{job_id}/resume")
        assert resp.status_code == 409


class TestAeoFanout:
    async def test_gap_analysis_failure_returns_503(self, client):
        sub_queries = [SubQuery(type=SubQueryType.HOW_TO, query="how to use a CRM")]

        with (
            patch(
                "app.aeo.routes.generate_sub_queries",
                new=AsyncMock(return_value=(sub_queries, "test-model")),
            ),
            patch("app.aeo.routes.analyze_gaps", side_effect=LlmError("Voyage down")),
            patch("app.aeo.routes.save_aeo_analysis", new=AsyncMock()),
        ):
            resp = await client.post(
                "/api/aeo/fanout",
                json={
                    "target_query": "best crm for startups",
                    "existing_content": "This is existing content with enough words to analyze.",
                },
            )

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert detail["error"] == "llm_unavailable"
        assert "Voyage down" in detail["detail"]
