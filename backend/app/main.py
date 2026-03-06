"""FastAPI application factory for LabLink.

Creates and configures the FastAPI app with:
- CORS middleware for cross-origin requests
- Exception handlers that return Envelope responses with suggestions
- Health check router
- Request ID middleware
"""

from __future__ import annotations

import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.exceptions import LabLinkError
from app.schemas.envelope import Envelope, ErrorDetail, ResponseMeta

logger = logging.getLogger("lablink")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()
    logger.info(
        "LabLink %s starting in %s mode",
        settings.version,
        settings.environment.value,
    )
    yield
    logger.info("LabLink shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Args:
        settings: Optional settings override (useful for testing).

    Returns:
        Configured FastAPI application.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Agent-native lab data integration platform",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url="/redoc" if settings.is_dev else None,
    )

    # --- Middleware ---
    _add_cors(app, settings)
    _add_request_id_middleware(app)

    # --- Exception Handlers ---
    _add_exception_handlers(app)

    # --- Routers ---
    _include_routers(app)

    return app


def _add_cors(app: FastAPI, settings: Settings) -> None:
    """Configure CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )


def _add_request_id_middleware(app: FastAPI) -> None:
    """Add middleware that attaches a unique request ID to each request/response."""

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception as exc:
            # Unhandled exceptions bubble up past Starlette's exception middleware
            # when using BaseHTTPMiddleware. Catch them here to return envelope.
            logger.exception("Unhandled exception: %s", exc)
            envelope = Envelope.single_error(
                code="internal_error",
                message="An unexpected error occurred.",
                suggestion="Retry the request. If the problem persists, contact support with the request ID.",
                request_id=request_id,
            )
            response = JSONResponse(
                status_code=500,
                content=envelope.model_dump(mode="json"),
            )
        response.headers["X-Request-ID"] = request_id
        return response


def _add_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers that return Envelope error responses."""

    @app.exception_handler(LabLinkError)
    async def lablink_error_handler(request: Request, exc: LabLinkError) -> JSONResponse:
        """Handle all LabLink domain errors."""
        request_id = getattr(request.state, "request_id", None)
        envelope = Envelope.single_error(
            code=exc.code,
            message=exc.message,
            suggestion=exc.suggestion,
            field=exc.field,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle standard HTTP exceptions."""
        request_id = getattr(request.state, "request_id", None)

        suggestion = _get_http_suggestion(exc.status_code)
        envelope = Envelope.single_error(
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            suggestion=suggestion,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic/FastAPI validation errors."""
        request_id = getattr(request.state, "request_id", None)

        errors = []
        for err in exc.errors():
            field_path = " -> ".join(str(loc) for loc in err.get("loc", []))
            errors.append(
                ErrorDetail(
                    code="validation_error",
                    message=err.get("msg", "Validation failed"),
                    field=field_path or None,
                    suggestion=f"Check the '{field_path}' field. Expected type: {err.get('type', 'unknown')}.",
                )
            )

        envelope = Envelope.error(errors, request_id=request_id)
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled exceptions."""
        request_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled exception: %s", exc)
        envelope = Envelope.single_error(
            code="internal_error",
            message="An unexpected error occurred.",
            suggestion="Retry the request. If the problem persists, contact support with the request ID.",
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(mode="json"),
        )


def _get_http_suggestion(status_code: int) -> str:
    """Return agent-friendly suggestion for common HTTP status codes."""
    suggestions = {
        400: "Check the request body and query parameters for syntax errors.",
        401: "Provide a valid JWT token in the Authorization header as 'Bearer <token>'.",
        403: "Your token lacks the required scope. Request an upgraded token or contact an admin.",
        404: "Check the URL path and resource ID. Use the list endpoint to discover valid IDs.",
        405: "This HTTP method is not supported for this endpoint. Check the API docs at /docs.",
        409: "A conflict occurred. The resource may already exist or be in an incompatible state.",
        429: "Rate limit exceeded. Wait and retry with exponential backoff.",
        500: "Retry the request. If the problem persists, contact support with the request ID.",
    }
    return suggestions.get(status_code, "Check the API documentation at /docs for guidance.")


def _include_routers(app: FastAPI) -> None:
    """Register all API routers."""
    from app.routers.audit import router as audit_router
    from app.routers.auth import router as auth_router
    from app.routers.experiments import router as experiments_router
    from app.routers.files import router as files_router
    from app.routers.health import router as health_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(experiments_router, prefix="/api/v1")
