"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, entities, graph, health, ingestion, nlquery, papers, rag, search
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.resources import Resources

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info("app.startup", env=settings.app_env)
    # Connections are lazy; startup does not fail if a database is still booting.
    # /api/health/ready reports dependency status.
    resources: Resources | None = None
    if not hasattr(app.state, "graph"):
        resources = Resources.create(settings)
        app.state.graph = resources.graph
        app.state.sessions = resources.sessions
    try:
        yield
    finally:
        if getattr(app.state, "arq", None) is not None:
            await app.state.arq.aclose()
        if resources is not None:
            await resources.close()
        log.info("app.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description="Research intelligence over a citation knowledge graph.",
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
    )
    app.state.settings = settings

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_error_handlers(app)
    for router in (
        health.router,
        papers.router,
        entities.router,
        graph.router,
        search.router,
        rag.router,
        nlquery.router,
        analytics.router,
        analytics.runs,
        ingestion.router,
    ):
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
