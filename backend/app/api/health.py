from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import GraphDep, SessionsDep
from app.core.config import get_settings
from app.core.errors import DependencyUnavailableError

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/health/ready", summary="Readiness probe (checks backing services)")
async def ready(graph: GraphDep, sessions: SessionsDep) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        await graph.verify()
        checks["neo4j"] = "ok"
    except DependencyUnavailableError as exc:
        checks["neo4j"] = f"unavailable: {exc.message}"
    try:
        async with sessions() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except (SQLAlchemyError, OSError) as exc:
        checks["postgres"] = f"unavailable: {type(exc).__name__}"
    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
