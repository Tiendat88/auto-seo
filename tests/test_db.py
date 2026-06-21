from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db import (
    _INIT_DB_LOCK_ID,
    _SCHED_LOCK_ID,
    _acquire_init_lock,
    try_acquire_scheduler_lock,
)


@pytest.mark.asyncio
async def test_acquire_init_lock_uses_postgres_advisory_lock() -> None:
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=AsyncMock(),
    )

    await _acquire_init_lock(conn)

    conn.execute.assert_awaited_once()
    stmt = conn.execute.await_args.args[0]
    params = conn.execute.await_args.args[1]
    assert "pg_advisory_xact_lock" in str(stmt)
    assert params == {"lock_id": _INIT_DB_LOCK_ID}


@pytest.mark.asyncio
async def test_acquire_init_lock_skips_non_postgres() -> None:
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite"),
        execute=AsyncMock(),
    )

    await _acquire_init_lock(conn)

    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_lock_postgres_true() -> None:
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: True)),
    )

    assert await try_acquire_scheduler_lock(conn) is True

    stmt = conn.execute.await_args.args[0]
    params = conn.execute.await_args.args[1]
    assert "pg_try_advisory_lock" in str(stmt)
    assert params == {"lock_id": _SCHED_LOCK_ID}


@pytest.mark.asyncio
async def test_scheduler_lock_postgres_false_when_held() -> None:
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: False)),
    )

    assert await try_acquire_scheduler_lock(conn) is False


@pytest.mark.asyncio
async def test_scheduler_lock_sqlite_always_leader() -> None:
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite"),
        execute=AsyncMock(),
    )

    assert await try_acquire_scheduler_lock(conn) is True
    conn.execute.assert_not_awaited()
