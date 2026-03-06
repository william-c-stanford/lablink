"""Response envelope schema for all API responses.

Every endpoint returns data wrapped in Envelope[T] for agent-native consistency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata included in every response envelope."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str | None = None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


class ErrorDetail(BaseModel):
    """Structured error detail with agent-friendly suggestion field."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(None, description="Field that caused the error, if applicable")
    suggestion: str | None = Field(
        None,
        description="Agent-friendly suggestion for how to recover from this error",
    )


class Envelope(BaseModel, Generic[T]):
    """Standard response wrapper for all API endpoints.

    All endpoints return {data, meta, errors} for consistent agent consumption.
    """

    data: T | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    errors: list[ErrorDetail] = Field(default_factory=list)

    @classmethod
    def ok(
        cls,
        data: T,
        *,
        request_id: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        total: int | None = None,
    ) -> Envelope[T]:
        """Create a successful response envelope."""
        return cls(
            data=data,
            meta=ResponseMeta(
                request_id=request_id,
                page=page,
                page_size=page_size,
                total=total,
            ),
        )

    @classmethod
    def error(
        cls,
        errors: list[ErrorDetail],
        *,
        request_id: str | None = None,
    ) -> Envelope[None]:
        """Create an error response envelope."""
        return cls(
            data=None,
            meta=ResponseMeta(request_id=request_id),
            errors=errors,
        )

    @classmethod
    def single_error(
        cls,
        code: str,
        message: str,
        *,
        suggestion: str | None = None,
        field: str | None = None,
        request_id: str | None = None,
    ) -> Envelope[None]:
        """Create an envelope with a single error."""
        return cls.error(
            [ErrorDetail(code=code, message=message, suggestion=suggestion, field=field)],
            request_id=request_id,
        )
