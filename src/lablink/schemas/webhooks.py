"""Pydantic schemas for Webhook CRUD and delivery tracking.

Aligned to the Webhook and WebhookDelivery ORM models in
lablink.models.event.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class WebhookCreate(BaseModel):
    """Request body to create a new webhook subscription."""

    url: str = Field(
        ...,
        max_length=2048,
        description="HTTPS endpoint URL that will receive POST requests",
    )
    events: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Event types to subscribe to, e.g. "
            "['upload.completed', 'parsing.completed', 'experiment.status_changed']"
        ),
    )
    secret: str | None = Field(
        default=None,
        max_length=255,
        description="Shared secret for HMAC-SHA256 payload signing. Auto-generated if omitted.",
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class WebhookUpdate(BaseModel):
    """Request body to partially update a webhook (PATCH semantics)."""

    url: str | None = Field(
        default=None,
        max_length=2048,
        description="New endpoint URL",
    )
    events: list[str] | None = Field(
        default=None,
        min_length=1,
        description="New list of subscribed event types",
    )
    is_active: bool | None = Field(
        default=None,
        description="Enable or disable the webhook",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> WebhookUpdate:
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class WebhookResponse(BaseModel):
    """Full webhook representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique webhook identifier")
    url: str = Field(..., description="Endpoint URL receiving events")
    events: list[str] = Field(..., description="Subscribed event types")
    is_active: bool = Field(..., description="Whether the webhook is currently active")
    created_by: uuid.UUID = Field(..., description="User who created the webhook")
    created_at: datetime = Field(..., description="Webhook creation timestamp")


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery attempt record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique delivery identifier")
    event_type: str = Field(..., description="Event type that triggered this delivery")
    status: str = Field(..., description="Delivery status: pending, delivered, failed")
    attempts: int = Field(..., description="Number of delivery attempts made")
    last_attempt_at: datetime | None = Field(None, description="Timestamp of the most recent attempt")
    response_status: int | None = Field(None, description="HTTP status code from the endpoint")
    created_at: datetime = Field(..., description="Delivery record creation timestamp")
