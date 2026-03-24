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
