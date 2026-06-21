"""Unit tests for the SEO lifecycle: state machine, scheduler tick, measurement, API."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.lifecycle.scheduler as sched
from app.db import Base, get_session
from app.job.models import Job, JobStatus
from app.lifecycle.measure import _measure_rank, decide_refresh, measure_lifecycle
from app.lifecycle.models import (
    Lifecycle,
    LifecycleMeasurement,
    LifecyclePhase,
    RefreshPolicy,
    utcnow,
)
from app.lifecycle.scheduler import tick
from app.lifecycle.service import advance_lifecycle, complete_measurement
from app.main import app
from app.serp.models import SerpData, SerpResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_lc(session: AsyncSession, **kw) -> Lifecycle:
    kw.setdefault("topic", "best crm software")
    lc = Lifecycle(**kw)
    session.add(lc)
    await session.commit()
    return lc


async def _make_job(session: AsyncSession, status: JobStatus) -> Job:
    job = Job(topic="best crm software", status=status)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


def _policy() -> RefreshPolicy:
    return RefreshPolicy(
        rank_threshold=3, aeo_threshold=65, brand_threshold=50.0, max_content_age_days=90
    )


class _StubSerp:
    def __init__(self, results: list[SerpResult]) -> None:
        self._results = results

    async def search(self, query: str) -> SerpData:
        return SerpData(query=query, results=self._results)


# ---------------------------------------------------------------------------
# decide_refresh — pure decision logic
# ---------------------------------------------------------------------------


def test_decide_refresh_healthy() -> None:
    decayed, reasons = decide_refresh(
        rank=1, aeo=90, brand=80.0, age_days=10, policy=_policy()
    )
    assert not decayed
    assert reasons == []


def test_decide_refresh_rank_drop() -> None:
    decayed, reasons = decide_refresh(
        rank=8, aeo=90, brand=80.0, age_days=10, policy=_policy()
    )
    assert decayed
    assert any("rank" in r for r in reasons)


def test_decide_refresh_aeo_low() -> None:
    decayed, reasons = decide_refresh(
        rank=1, aeo=40, brand=80.0, age_days=10, policy=_policy()
    )
    assert decayed
    assert any("aeo" in r for r in reasons)


def test_decide_refresh_stale() -> None:
    decayed, reasons = decide_refresh(
        rank=1, aeo=90, brand=80.0, age_days=120, policy=_policy()
    )
    assert decayed
    assert any("stale" in r for r in reasons)


def test_decide_refresh_brand_low() -> None:
    decayed, reasons = decide_refresh(
        rank=1, aeo=90, brand=10.0, age_days=10, policy=_policy()
    )
    assert decayed
    assert any("brand" in r for r in reasons)


def test_decide_refresh_ignores_none() -> None:
    decayed, reasons = decide_refresh(
        rank=None, aeo=None, brand=None, age_days=None, policy=_policy()
    )
    assert not decayed
    assert reasons == []


# ---------------------------------------------------------------------------
# State machine — advance_lifecycle
# ---------------------------------------------------------------------------


async def test_created_spawns_generation(session: AsyncSession) -> None:
    lc = await _make_lc(session, phase=LifecyclePhase.CREATED, cadence_days=0)
    spawn, dispatch = MagicMock(), MagicMock()

    await advance_lifecycle(session, lc, now=utcnow(), spawn=spawn, dispatch_measure=dispatch)

    assert lc.phase == LifecyclePhase.GENERATING
    assert lc.current_job_id is not None
    assert lc.cycle_count == 1
    spawn.assert_called_once_with(lc.current_job_id, lc.id)
    dispatch.assert_not_called()


async def test_generating_complete_oneshot_goes_done(session: AsyncSession) -> None:
    job = await _make_job(session, JobStatus.COMPLETED)
    lc = await _make_lc(
        session, phase=LifecyclePhase.GENERATING, cadence_days=0, current_job_id=job.id
    )

    await advance_lifecycle(
        session, lc, now=utcnow(), spawn=MagicMock(), dispatch_measure=MagicMock()
    )

    assert lc.phase == LifecyclePhase.DONE
    assert lc.next_run_at is None
    assert lc.last_refresh_at is not None


async def test_generating_complete_recurring_goes_monitoring(session: AsyncSession) -> None:
    job = await _make_job(session, JobStatus.COMPLETED)
    now = utcnow()
    lc = await _make_lc(
        session, phase=LifecyclePhase.GENERATING, cadence_days=7, current_job_id=job.id
    )

    await advance_lifecycle(
        session, lc, now=now, spawn=MagicMock(), dispatch_measure=MagicMock()
    )

    assert lc.phase == LifecyclePhase.MONITORING
    assert lc.next_run_at == now + timedelta(days=7)


async def test_generating_failed_goes_failed(session: AsyncSession) -> None:
    job = await _make_job(session, JobStatus.FAILED)
    lc = await _make_lc(
        session, phase=LifecyclePhase.GENERATING, cadence_days=7, current_job_id=job.id
    )

    await advance_lifecycle(
        session, lc, now=utcnow(), spawn=MagicMock(), dispatch_measure=MagicMock()
    )

    assert lc.phase == LifecyclePhase.FAILED
    assert lc.error is not None


async def test_generating_still_running_is_noop(session: AsyncSession) -> None:
    job = await _make_job(session, JobStatus.RESEARCHING)
    lc = await _make_lc(
        session, phase=LifecyclePhase.GENERATING, cadence_days=7, current_job_id=job.id
    )

    await advance_lifecycle(
        session, lc, now=utcnow(), spawn=MagicMock(), dispatch_measure=MagicMock()
    )

    assert lc.phase == LifecyclePhase.GENERATING


async def test_monitoring_due_dispatches_measure(session: AsyncSession) -> None:
    now = utcnow()
    lc = await _make_lc(
        session,
        phase=LifecyclePhase.MONITORING,
        cadence_days=7,
        next_run_at=now - timedelta(seconds=1),
    )
    dispatch = MagicMock()

    await advance_lifecycle(
        session, lc, now=now, spawn=MagicMock(), dispatch_measure=dispatch
    )

    assert lc.phase == LifecyclePhase.MEASURING
    dispatch.assert_called_once_with(lc.id)


async def test_monitoring_not_due_is_noop(session: AsyncSession) -> None:
    now = utcnow()
    lc = await _make_lc(
        session,
        phase=LifecyclePhase.MONITORING,
        cadence_days=7,
        next_run_at=now + timedelta(days=1),
    )
    dispatch = MagicMock()

    await advance_lifecycle(
        session, lc, now=now, spawn=MagicMock(), dispatch_measure=dispatch
    )

    assert lc.phase == LifecyclePhase.MONITORING
    dispatch.assert_not_called()


async def test_needs_refresh_spawns_generation(session: AsyncSession) -> None:
    lc = await _make_lc(session, phase=LifecyclePhase.NEEDS_REFRESH, cadence_days=7)
    spawn = MagicMock()

    await advance_lifecycle(
        session, lc, now=utcnow(), spawn=spawn, dispatch_measure=MagicMock()
    )

    assert lc.phase == LifecyclePhase.GENERATING
    spawn.assert_called_once()


async def test_paused_is_noop(session: AsyncSession) -> None:
    lc = await _make_lc(session, phase=LifecyclePhase.PAUSED, enabled=False)
    spawn = MagicMock()

    await advance_lifecycle(
        session, lc, now=utcnow(), spawn=spawn, dispatch_measure=MagicMock()
    )

    assert lc.phase == LifecyclePhase.PAUSED
    spawn.assert_not_called()


# ---------------------------------------------------------------------------
# complete_measurement — decision → transition
# ---------------------------------------------------------------------------


async def test_complete_measurement_decayed_needs_refresh(
    session: AsyncSession, monkeypatch
) -> None:
    lc = await _make_lc(session, phase=LifecyclePhase.MEASURING, cadence_days=7)

    async def fake_measure(sess, lifecycle, *, llm, serp, now):
        m = LifecycleMeasurement(
            lifecycle_id=lifecycle.id, rank_position=10, aeo_score=90, content_age_days=1
        )
        sess.add(m)
        return m

    monkeypatch.setattr("app.lifecycle.service.measure_lifecycle", fake_measure)

    m = await complete_measurement(
        session, lc, llm=MagicMock(), serp=MagicMock(), now=utcnow()
    )

    assert lc.phase == LifecyclePhase.NEEDS_REFRESH
    assert m.decayed
    assert any("rank" in r for r in (m.decay_reasons or []))


async def test_complete_measurement_healthy_keeps_monitoring(
    session: AsyncSession, monkeypatch
) -> None:
    now = utcnow()
    lc = await _make_lc(session, phase=LifecyclePhase.MEASURING, cadence_days=7)

    async def fake_measure(sess, lifecycle, *, llm, serp, now):
        m = LifecycleMeasurement(
            lifecycle_id=lifecycle.id, rank_position=1, aeo_score=90, content_age_days=1
        )
        sess.add(m)
        return m

    monkeypatch.setattr("app.lifecycle.service.measure_lifecycle", fake_measure)

    m = await complete_measurement(session, lc, llm=MagicMock(), serp=MagicMock(), now=now)

    assert lc.phase == LifecyclePhase.MONITORING
    assert not m.decayed
    assert lc.next_run_at == now + timedelta(days=7)


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


async def test_measure_rank_found() -> None:
    lc = Lifecycle(
        topic="t", published_url="https://example.com/post", measure_query="best crm"
    )
    serp = _StubSerp(
        [SerpResult(rank=4, url="https://example.com/post", title="T", snippet="s")]
    )
    assert await _measure_rank(lc, serp) == 4


async def test_measure_rank_absent() -> None:
    lc = Lifecycle(topic="t", published_url="https://example.com/post")
    serp = _StubSerp(
        [SerpResult(rank=1, url="https://other.com/x", title="T", snippet="s")]
    )
    assert await _measure_rank(lc, serp) is None


async def test_measure_rank_no_published_url() -> None:
    lc = Lifecycle(topic="t")
    assert await _measure_rank(lc, _StubSerp([])) is None


async def test_measure_lifecycle_persists_snapshot(
    session: AsyncSession, sample_article
) -> None:
    job = Job(topic="best crm software", status=JobStatus.COMPLETED)
    job.set_article(sample_article)
    session.add(job)
    await session.commit()
    await session.refresh(job)

    now = utcnow()
    lc = Lifecycle(topic="best crm software", current_job_id=job.id)
    lc.last_refresh_at = now - timedelta(days=5)
    session.add(lc)
    await session.commit()

    llm = AsyncMock()
    llm.generate_structured = AsyncMock(side_effect=Exception("no llm"))  # forces fallback
    serp = _StubSerp([SerpResult(rank=1, url="https://x.com", title="t", snippet="s")])

    m = await measure_lifecycle(session, lc, llm=llm, serp=serp, now=now)
    await session.commit()

    assert m.aeo_score is not None
    assert m.content_age_days == 5
    assert m.rank_position is None  # no published_url → rank not measured
    assert lc.last_aeo_score == m.aeo_score


# ---------------------------------------------------------------------------
# Scheduler tick
# ---------------------------------------------------------------------------


async def test_tick_advances_only_due(session: AsyncSession) -> None:
    now = utcnow()
    due = await _make_lc(
        session,
        phase=LifecyclePhase.MONITORING,
        cadence_days=7,
        next_run_at=now - timedelta(seconds=1),
    )
    not_due = await _make_lc(
        session,
        phase=LifecyclePhase.MONITORING,
        cadence_days=7,
        next_run_at=now + timedelta(days=1),
    )
    created = await _make_lc(
        session, phase=LifecyclePhase.CREATED, next_run_at=now - timedelta(seconds=1)
    )
    spawn, dispatch = MagicMock(), MagicMock()

    advanced = await tick(session, now=now, spawn=spawn, dispatch_measure=dispatch)

    assert due.id in advanced
    assert created.id in advanced
    assert not_due.id not in advanced
    spawn.assert_called_once()
    dispatch.assert_called_once_with(due.id)


async def test_tick_respects_concurrency_cap(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(sched.settings, "lifecycle_max_concurrent", 1)
    monkeypatch.setattr(sched.settings, "lifecycle_batch_size", 50)
    now = utcnow()

    running_job = await _make_job(session, JobStatus.RESEARCHING)
    gen = await _make_lc(
        session,
        phase=LifecyclePhase.GENERATING,
        cadence_days=7,
        current_job_id=running_job.id,
        next_run_at=now - timedelta(seconds=1),
    )
    c1 = await _make_lc(
        session, phase=LifecyclePhase.CREATED, next_run_at=now - timedelta(seconds=1)
    )
    c2 = await _make_lc(
        session, phase=LifecyclePhase.CREATED, next_run_at=now - timedelta(seconds=1)
    )
    spawn = MagicMock()

    advanced = await tick(
        session, now=now, spawn=spawn, dispatch_measure=MagicMock()
    )

    # in_flight already at cap (1 GENERATING) → no new generation spawned
    spawn.assert_not_called()
    assert gen.id in advanced
    assert c1.id not in advanced
    assert c2.id not in advanced


# ---------------------------------------------------------------------------
# API smoke
# ---------------------------------------------------------------------------


@pytest.fixture
async def lc_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with (
        patch("app.lifecycle.routes.spawn_generation"),
        patch("app.lifecycle.routes.dispatch_measurement"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_create_list_get_pause_resume(lc_client) -> None:
    resp = await lc_client.post(
        "/api/lifecycles",
        json={"topic": "best crm software", "cadence_days": 7, "generate_now": False},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["phase"] == "created"
    lc_id = data["id"]

    resp = await lc_client.get("/api/lifecycles")
    assert resp.status_code == 200
    assert any(x["id"] == lc_id for x in resp.json()["lifecycles"])

    resp = await lc_client.get(f"/api/lifecycles/{lc_id}")
    assert resp.status_code == 200

    resp = await lc_client.post(f"/api/lifecycles/{lc_id}/pause")
    body = resp.json()
    assert body["phase"] == "paused"
    assert body["enabled"] is False

    resp = await lc_client.post(f"/api/lifecycles/{lc_id}/resume")
    assert resp.json()["enabled"] is True


async def test_create_generate_now_spawns_first_cycle(lc_client) -> None:
    resp = await lc_client.post(
        "/api/lifecycles",
        json={"topic": "best crm software", "generate_now": True},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["phase"] == "generating"
    assert data["current_job_id"]


async def test_tick_endpoint_requires_debug(lc_client) -> None:
    resp = await lc_client.post("/api/lifecycles/tick")
    assert resp.status_code == 404
