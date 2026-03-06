"""FastAPI application factory with CORS, exception handlers, and envelope middleware.

Creates the LabLink FastAPI app with:
- CORS middleware configured from settings
- Global exception handlers that wrap all errors in Envelope[None]
- Request-ID middleware for tracing
- Health check endpoint
- Router registration (when routers are available)

Usage::

    # Development server
    uvicorn lablink.main:app --reload

    # Or via the factory
    from lablink.main import create_app
    app = create_app()
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from lablink.config import get_settings
from lablink.exceptions import LabLinkError
from lablink.schemas.envelope import Envelope, ErrorDetail, ResponseMeta

logger = logging.getLogger("lablink")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    settings = get_settings()
    logger.info(
        "LabLink %s starting (env=%s, debug=%s)",
        settings.version,
        settings.environment.value,
        settings.debug,
    )
    yield
    logger.info("LabLink shutting down")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

def _error_envelope(
    status_code: int,
    *,
    code: str,
    message: str,
    field: str | None = None,
    suggestion: str | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Build a JSON response with the standard Envelope error shape."""
    envelope = Envelope(
        data=None,
        meta=ResponseMeta(request_id=request_id or str(uuid.uuid4())),
        errors=[
            ErrorDetail(
                code=code,
                message=message,
                field=field,
                suggestion=suggestion,
            )
        ],
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wrap FastAPI/Starlette HTTPExceptions in the standard envelope."""
    request_id = getattr(request.state, "request_id", None)

    # Map common HTTP status codes to machine-readable error codes
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
    }
    error_code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")

    # Provide agent-actionable suggestions for common errors
    suggestion_map = {
        401: "Include a valid Bearer token in the Authorization header.",
        403: "Check your role permissions with get_current_user.",
        404: "Use the appropriate list endpoint to find valid resource IDs.",
        429: "Retry after the Retry-After header value.",
    }
    suggestion = suggestion_map.get(exc.status_code)

    return _error_envelope(
        exc.status_code,
        code=error_code,
        message=str(exc.detail),
        suggestion=suggestion,
        request_id=request_id,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Wrap Pydantic validation errors in the standard envelope."""
    request_id = getattr(request.state, "request_id", None)

    errors: list[ErrorDetail] = []
    for err in exc.errors():
        loc = " -> ".join(str(part) for part in err.get("loc", []))
        errors.append(
            ErrorDetail(
                code="VALIDATION_ERROR",
                message=err.get("msg", "Validation error"),
                field=loc or None,
                suggestion="Check the request body/parameters against the API schema.",
            )
        )

    envelope = Envelope(
        data=None,
        meta=ResponseMeta(request_id=request_id or str(uuid.uuid4())),
        errors=errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=envelope.model_dump(mode="json"),
    )


async def lablink_exception_handler(
    request: Request, exc: LabLinkError
) -> JSONResponse:
    """Handle LabLinkError subclasses with structured Envelope responses."""
    request_id = getattr(request.state, "request_id", None)
    return _error_envelope(
        exc.status_code,
        code=exc.code,
        message=exc.message,
        field=exc.field,
        suggestion=exc.suggestion,
        request_id=request_id,
    )


async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled exception (request_id=%s)", request_id)

    settings = get_settings()
    message = str(exc) if settings.debug else "An internal error occurred."

    return _error_envelope(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message=message,
        suggestion="If this persists, contact support with the request_id.",
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID to every request for tracing.

    Also acts as a catch-all for unhandled exceptions that escape
    FastAPI's exception handler layer (e.g. errors raised inside
    middleware or streaming responses).
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception in middleware (rid=%s)", request_id)
        settings = get_settings()
        response = _error_envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="An internal error occurred." if not settings.debug else "Internal server error",
            suggestion="If this persists, contact support with the request_id.",
            request_id=request_id,
        )
    elapsed_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

    logger.debug(
        "%s %s -> %s (%.1fms, rid=%s)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(settings=None) -> FastAPI:
    """Create and configure the LabLink FastAPI application.

    Args:
        settings: Optional Settings override (useful for testing).

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Agent-native lab data integration platform",
        docs_url="/docs" if settings.is_dev else None,
        redoc_url="/redoc" if settings.is_dev else None,
        openapi_url="/openapi.json" if settings.is_dev else "/api/openapi.json",
        lifespan=lifespan,
    )

    # -- CORS --
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )

    # -- Request ID middleware --
    application.middleware("http")(request_id_middleware)

    # -- Exception handlers --
    application.add_exception_handler(
        StarletteHTTPException, http_exception_handler
    )
    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    application.add_exception_handler(LabLinkError, lablink_exception_handler)
    application.add_exception_handler(Exception, generic_exception_handler)

    # -- Health check --
    @application.get(
        "/health",
        tags=["system"],
        response_model=Envelope[dict],
        operation_id="check_health",
    )
    async def health_check() -> Envelope[dict]:
        """Health check endpoint for load balancers and monitoring."""
        return Envelope(
            data={
                "status": "healthy",
                "version": settings.version,
                "environment": settings.environment.value,
            }
        )

    # -- API v1 router registration --
    # Routers are registered here as they are built.
    # Example:
    #   from lablink.routers import auth, organizations, ...
    #   application.include_router(auth.router, prefix="/api/v1")
    _register_routers(application)

    return application


def _register_routers(application: FastAPI) -> None:
    """Register all available API routers.

    Each router is imported inside a try/except so the app can boot
    even if some modules aren't built yet.
    """
    router_modules = [
        ("lablink.routers.auth", "/api/v1"),
        ("lablink.routers.organizations", "/api/v1"),
        ("lablink.routers.projects", "/api/v1"),
        ("lablink.routers.instruments", "/api/v1"),
        ("lablink.routers.agents", "/api/v1"),
        ("lablink.routers.uploads", "/api/v1"),
        ("lablink.routers.data", "/api/v1"),
        ("lablink.routers.experiments", "/api/v1"),
        ("lablink.routers.campaigns", "/api/v1"),
        ("lablink.routers.webhooks", "/api/v1"),
        ("lablink.routers.audit", "/api/v1"),
        ("lablink.routers.admin", "/api/v1"),
    ]

    for module_path, prefix in router_modules:
        try:
            import importlib

            mod = importlib.import_module(module_path)
            router = getattr(mod, "router", None)
            if router is not None:
                application.include_router(router, prefix=prefix)
                logger.debug("Registered router: %s", module_path)
        except (ImportError, ModuleNotFoundError):
            logger.debug("Router not available yet: %s", module_path)


# ---------------------------------------------------------------------------
# Module-level app instance (for uvicorn lablink.main:app)
# ---------------------------------------------------------------------------

app = create_app()
