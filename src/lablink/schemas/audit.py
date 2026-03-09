"""Pydantic schemas for audit events and chain verification.

Aligned to the AuditEvent ORM model in lablink.models.event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditEventCreate(BaseModel):
    """Schema for creating an audit event."""

    organization_id: str = Field(..., description="Organization scope for the event")
    actor_type: str = Field(
        "user",
        max_length=20,
        description="Category of actor: 'user', 'agent', or 'system'",
    )
    actor_id: Optional[str] = Field(
        None,
        description="UUID of the acting user or agent",
    )
    action: str = Field(
        ...,
        max_length=100,
        description="Action verb, e.g. 'upload.created', 'experiment.status_changed'",
    )
    resource_type: str = Field(
        ...,
        max_length=50,
        description="Type of resource affected (e.g. 'upload', 'experiment')",
    )
    resource_id: str = Field(
        ...,
        description="UUID of the affected resource",
    )
    details: Optional[dict[str, Any]] = Field(
        None,
        description="Before/after values, context",
    )
    ip_address: Optional[str] = Field(
        None,
        max_length=45,
        description="Client IP address",
    )
    user_agent: Optional[str] = Field(
        None,
        description="Client user-agent string",
    )


class AuditEventRead(BaseModel):
    """Schema for reading an audit event."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    organization_id: uuid.UUID
    actor_type: str
    actor_id: Optional[uuid.UUID] = None
    action: str
    resource_type: str
    resource_id: uuid.UUID
    details: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    hash: str
    created_at: datetime


class AuditChainLink(BaseModel):
    """A single link in the chain verification result."""

    sequence: int
    id: str
    expected_hash: str
    stored_hash: str
    valid: bool


class AuditChainVerification(BaseModel):
    """Response for audit chain integrity verification."""

    valid: bool = Field(..., description="Whether the entire chain is intact")
    total_entries: int = Field(..., description="Total entries verified")
    invalid_entries: int = Field(0, description="Number of broken entries")
    first_invalid_id: Optional[str] = Field(
        None,
        description="ID of the first invalid entry, if any",
    )
    details: list[AuditChainLink] = Field(
        default_factory=list,
        description="Per-entry verification details",
    )
    suggestion: Optional[str] = Field(
        None,
        description="Agent-friendly suggestion if chain is broken",
    )


# ---------------------------------------------------------------------------
# Router-facing response & query params
# ---------------------------------------------------------------------------


class AuditEventResponse(BaseModel):
    """Audit event representation returned by API endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID = Field(..., description="Unique audit event identifier")
    actor_type: str = Field(..., description="Category of actor: user, agent, or system")
    actor_id: Optional[uuid.UUID] = Field(None, description="UUID of the acting user or agent")
    action: str = Field(..., description="Action verb, e.g. 'upload.created'")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: uuid.UUID = Field(..., description="UUID of the affected resource")
    details: Optional[dict[str, Any]] = Field(None, description="Before/after values and context")
    created_at: datetime = Field(..., description="When the event occurred")


class AuditListParams(BaseModel):
    """Query parameters for listing audit events with filtering and pagination."""

    resource_type: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Filter by resource type (e.g. 'upload', 'experiment')",
    )
    resource_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Filter by specific resource ID",
    )
    actor_type: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Filter by actor type: user, agent, or system",
    )
    created_after: Optional[datetime] = Field(
        default=None,
        description="Only include events created after this timestamp (UTC)",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (1-indexed)",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (max 100)",
    )
