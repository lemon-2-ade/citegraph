"""Process-wide resources shared by the API, the worker and the CLI."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.session import create_engine, create_sessionmaker
from app.graph.client import GraphClient


@dataclass
class Resources:
    settings: Settings
    graph: GraphClient
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]

    @classmethod
    def create(cls, settings: Settings) -> Resources:
        engine = create_engine(settings.database_url.get_secret_value())
        return cls(
            settings=settings,
            graph=GraphClient.from_settings(settings),
            engine=engine,
            sessions=create_sessionmaker(engine),
        )

    async def close(self) -> None:
        await self.graph.close()
        await self.engine.dispose()
