"""Domain errors and their HTTP mapping."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger(__name__)


class ResearchGraphError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ResearchGraphError):
    status_code = 404
    code = "not_found"


class ValidationFailedError(ResearchGraphError):
    status_code = 422
    code = "validation_failed"


class DependencyUnavailableError(ResearchGraphError):
    """A backing service (Neo4j, PostgreSQL, Redis, external API) is unavailable."""

    status_code = 503
    code = "dependency_unavailable"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResearchGraphError)
    async def _handle(_: Request, exc: ResearchGraphError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("error.domain", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
