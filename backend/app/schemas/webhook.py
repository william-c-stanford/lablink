"""Pydantic schemas for Webhook CRUD and delivery tracking.

Webhooks allow organisations to receive real-time HTTP callbacks when
events occur (e.g. upload.completed, parsing.completed,
experiment.status_changed).  Each delivery attempt is logged for
debugging and retry visibility.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WebhookEvent(str, Enum):
    """Supported webhook event types."""

    UPLOAD_COMPLETED = "upload.completed"
    PARSING_COMPLETED = "parsing.completed"
    PARSING_FAILED = "parsing.failed"
    EXPERIMENT_CREATED = "experiment.created"
    EXPERIMENT_STATUS_CHANGED = "experiment.status_changed"
    EXPERIMENT_COMPLETED = "experiment.completed"
    CAMPAIGN_COMPLETED = "campaign.completed"


class DeliveryStatus(str, Enum):
    """Webhook delivery attempt statuses."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class WebhookCreate(BaseModel):
    """Request body to register a new webhook subscription.

    The ``secret`` is used for HMAC-SHA256 payload signing so the
    receiver can verify authenticity.
    """

    url: str = Field(
        ...,
        max_length=2048,
        description="HTTPS endpoint that will receive POST callbacks",
    )
    secret: str = Field(
        ...,
        min_length=16,
        max_length=255,
        description="Shared secret for HMAC-SHA256 signature verification (min 16 chars)",
    )
    events: list[WebhookEvent] = Field(
        ...,
        min_length=1,
        description="List of event types to subscribe to",
    )

    @field_validator("url")
    @classmethod
    def url_must_be_https(cls, v: str) -> str:
        """Validate that the webhook URL uses HTTPS (relaxed in dev for localhost)."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Webhook URL must not be blank")
        # Allow http://localhost and http://127.0.0.1 for local dev
        if stripped.startswith("http://localhost") or stripped.startswith("http://127.0.0.1"):
            return stripped
        if not stripped.startswith("https://"):
            raise ValueError(
                "Webhook URL must use HTTPS. "
                "Use http://localhost for local development."
            )
        return stripped

    @field_validator("events")
    @classmethod
    def no_duplicate_events(cls, v: list[WebhookEvent]) -> list[WebhookEvent]:
        """Ensure no duplicate event subscriptions."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate event types are not allowed")
        return v


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class WebhookUpdate(BaseModel):
    """Request body to update a webhook subscription (PATCH semantics).

    All fields are optional — only provided fields are updated.
    The ``secret`` can be rotated by providing a new value.
    """

    url: str | None = Field(
        None,
        max_length=2048,
        description="Updated callback URL",
    )
    secret: str | None = Field(
        None,
        min_length=16,
        max_length=255,
        description="New secret for HMAC-SHA256 signing",
    )
    events: list[WebhookEvent] | None = Field(
        None,
        min_length=1,
        description="Updated list of subscribed event types",
    )
    is_active: bool | None = Field(
        None,
        description="Enable or disable the webhook without deleting it",
    )

    @field_validator("url")
    @classmethod
    def url_must_be_https(cls, v: str | None) -> str | None:
        """Validate HTTPS when URL is provided."""
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Webhook URL must not be blank")
            if stripped.startswith("http://localhost") or stripped.startswith("http://127.0.0.1"):
                return stripped
            if not stripped.startswith("https://"):
                raise ValueError(
                    "Webhook URL must use HTTPS. "
                    "Use http://localhost for local development."
                )
            return stripped
        return v

    @field_validator("events")
    @classmethod
    def no_duplicate_events(cls, v: list[WebhookEvent] | None) -> list[WebhookEvent] | None:
        """Ensure no duplicate event subscriptions when provided."""
        if v is not None and len(v) != len(set(v)):
            raise ValueError("Duplicate event types are not allowed")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> WebhookUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class WebhookRead(BaseModel):
    """Webhook subscription returned by API endpoints.

    Note: ``secret`` is never exposed in read responses.
    """

    model_config = {"from_attributes": True}

    id: str
    org_id: str
    url: str
    events: list[str] = Field(
        default_factory=list,
        description="Subscribed event types",
    )
    is_active: bool = True
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class WebhookListResponse(BaseModel):
    """Paginated list of webhook subscriptions."""

    items: list[WebhookRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Webhook Delivery schemas
# ---------------------------------------------------------------------------


class WebhookDeliveryRead(BaseModel):
    """A single webhook delivery attempt record."""

    model_config = {"from_attributes": True}

    id: str
    webhook_id: str
    event_type: str
    payload: dict[str, Any] | None = None
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    last_attempt_at: datetime | None = None
    response_status: int | None = None
    response_body: str | None = None
    created_at: datetime


class WebhookDeliveryListResponse(BaseModel):
    """Paginated list of webhook delivery attempts."""

    items: list[WebhookDeliveryRead]
    total: int
    page: int
    page_size: int
