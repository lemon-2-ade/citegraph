"""FastAPI dependencies that expose shared resources stored on ``app.state``."""

from __future__ import annotations

import secrets
from typing import Annotated

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embeddings import EmbedderCache
from app.ai.llm import LLMCache
from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.graph.client import GraphClient

log = get_logger(__name__)


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_graph(request: Request) -> GraphClient:
    graph: GraphClient = request.app.state.graph
    return graph


def get_embedder(request: Request) -> EmbedderCache:
    embedder: EmbedderCache | None = getattr(request.app.state, "embedder", None)
    if embedder is None:
        embedder = EmbedderCache(request.app.state.settings)
        request.app.state.embedder = embedder
    return embedder


def get_llm(request: Request) -> LLMCache:
    llm: LLMCache | None = getattr(request.app.state, "llm", None)
    if llm is None:
        llm = LLMCache(request.app.state.settings)
        request.app.state.llm = llm
    return llm


def get_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    return sessions


async def get_queue(request: Request) -> ArqRedis:
    pool: ArqRedis | None = getattr(request.app.state, "arq", None)
    if pool is None:
        settings: Settings = request.app.state.settings
        try:
            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        except (OSError, ConnectionError) as exc:
            raise DependencyUnavailableError(f"Task queue unavailable: {exc}") from exc
        request.app.state.arq = pool
    return pool


def require_admin(request: Request, x_admin_token: Annotated[str | None, Header()] = None) -> None:
    settings: Settings = request.app.state.settings
    expected = settings.admin_api_token
    if expected is None:
        if settings.app_env == "production":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrative API is disabled")
        return
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token.encode(), expected.get_secret_value().encode()
    ):
        log.warning("auth.admin_rejected", path=request.url.path)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-Admin-Token")


LLMDep = Annotated[LLMCache, Depends(get_llm)]
EmbedderDep = Annotated[EmbedderCache, Depends(get_embedder)]
GraphDep = Annotated[GraphClient, Depends(get_graph)]
SessionsDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessions)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]
AdminDep = Depends(require_admin)
