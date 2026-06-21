from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, expire_on_commit=False)
_INIT_DB_LOCK_ID = 0x6175746F73656F  # "autoseo"
_SCHED_LOCK_ID = 0x6175746F73636864  # "autosched"


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def _acquire_init_lock(conn: AsyncConnection) -> None:
    """Serialize schema bootstrap across concurrent Postgres workers."""
    if conn.dialect.name != "postgresql":
        return
    await conn.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": _INIT_DB_LOCK_ID},
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await _acquire_init_lock(conn)
        await conn.run_sync(Base.metadata.create_all)


async def try_acquire_scheduler_lock(conn: AsyncConnection) -> bool:
    """Non-blocking, session-scoped leader election for the lifecycle scheduler.

    Only one Postgres backend can hold the advisory lock at a time, so exactly one
    uvicorn worker becomes the scheduler leader. The lock is held for the lifetime of
    the connection and auto-released if that connection drops (leader crash/restart),
    letting another worker take over. On SQLite/tests there is a single process, so we
    always grant leadership.
    """
    if conn.dialect.name != "postgresql":
        return True
    row = await conn.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": _SCHED_LOCK_ID},
    )
    return bool(row.scalar())
