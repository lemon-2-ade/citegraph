from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    kwargs: dict[str, object] = {"echo": echo}
    if not url.startswith("sqlite"):
        kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True)
    return create_async_engine(url, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    """Create all tables if missing.

    Schema migrations (Alembic) are not set up yet; ``create_all`` is idempotent for new
    tables but will not alter existing ones.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
