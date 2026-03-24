from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db import _INIT_DB_LOCK_ID, _acquire_init_lock


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
