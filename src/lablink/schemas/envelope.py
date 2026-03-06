"""Response envelope for all API endpoints.

Every LabLink endpoint returns an Envelope[T] wrapper providing consistent
structure for data, metadata, and errors. The ``suggestion`` field on
ErrorDetail is agent-actionable, enabling MCP tool consumers to self-correct.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata included when listing resources."""

    total_count: int = Field(..., description="Total number of items matching the query")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    has_more: bool = Field(..., description="Whether additional pages exist")


class ErrorDetail(BaseModel):
    """Structured error detail with agent-actionable suggestion."""

    code: str = Field(..., description="Machine-readable error code, e.g. 'EXPERIMENT_NOT_FOUND'")
    message: str = Field(..., description="Human-readable error description")
    field: Optional[str] = Field(
        default=None, description="Request field that caused the error, if applicable"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Agent-actionable hint, e.g. 'Use list_experiments to find valid IDs'",
    )
    retry: bool = Field(default=False, description="Whether the client should retry the request")
    retry_after: Optional[int] = Field(
        default=None, description="Seconds to wait before retrying, if retry is True"
    )


class ResponseMeta(BaseModel):
    """Metadata included in every API response."""

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this request (UUID v4)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Server timestamp when response was generated",
    )
    pagination: Optional[PaginationMeta] = Field(
        default=None, description="Pagination info, present only for list endpoints"
    )


class Envelope(BaseModel, Generic[T]):
    """Standard response wrapper for all LabLink API endpoints.

    Usage::

        @router.get("/items/{id}")
        async def get_item(id: UUID) -> Envelope[ItemSchema]:
            item = await service.get(id)
            return Envelope(data=item)

        # Error response:
        return Envelope(errors=[
            ErrorDetail(
                code="ITEM_NOT_FOUND",
                message=f"No item with ID '{id}'",
                suggestion="Use list_items to find valid IDs",
            )
        ])
    """

    data: Optional[T] = Field(default=None, description="Response payload")
    meta: ResponseMeta = Field(default_factory=ResponseMeta, description="Response metadata")
    errors: list[ErrorDetail] = Field(
        default_factory=list, description="List of errors, empty on success"
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def success_response(
    data: Any,
    pagination: PaginationMeta | None = None,
) -> Envelope:
    """Build a successful Envelope response.

    Args:
        data: The response payload.
        pagination: Optional pagination metadata for list endpoints.

    Returns:
        Envelope with data and metadata populated.
    """
    meta = ResponseMeta(pagination=pagination)
    return Envelope(data=data, meta=meta)


def error_response(
    code: str,
    message: str,
    *,
    suggestion: str | None = None,
    status: int = 400,
) -> JSONResponse:
    """Build an error Envelope wrapped in a JSONResponse.

    Args:
        code: Machine-readable error code (e.g. ``"NOT_FOUND"``).
        message: Human-readable error description.
        suggestion: Agent-actionable recovery hint.
        status: HTTP status code for the response.

    Returns:
        JSONResponse containing an Envelope with the error details.
    """
    envelope = Envelope(
        data=None,
        errors=[
            ErrorDetail(
                code=code,
                message=message,
                suggestion=suggestion,
            )
        ],
    )
    return JSONResponse(
        status_code=status,
        content=envelope.model_dump(mode="json"),
    )
