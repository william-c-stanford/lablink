"""Pydantic schemas for audit events and chain verification."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.system import AuditAction


class AuditEventCreate(BaseModel):
    """Schema for creating an audit log entry."""

    action: AuditAction = Field(..., description="The audit action type")
    resource_type: str = Field(
        ..., max_length=64, description="Type of resource affected (e.g. 'experiment', 'file')"
    )
    resource_id: str | None = Field(
        None, max_length=36, description="UUID of the affected resource"
    )
    actor_id: str | None = Field(
        None, max_length=36, description="UUID of the user or agent performing the action"
    )
    actor_type: str = Field(
        "user",
        max_length=32,
        description="Type of actor: 'user', 'system', or 'agent'",
    )
    summary: str = Field(
        ..., max_length=512, description="Human-readable summary of the event"
    )
    detail: str | None = Field(
        None, description="Extended detail or diff for the event"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Arbitrary JSON metadata for the event"
    )


class AuditEventRead(BaseModel):
    """Schema for reading an audit log entry."""

    model_config = {"from_attributes": True}

    id: str = Field(..., description="Unique audit event ID")
    sequence: int = Field(..., description="Monotonically increasing sequence number")
    action: str = Field(..., description="The audit action type")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: str | None = Field(None, description="UUID of the affected resource")
    actor_id: str | None = Field(None, description="UUID of the actor")
    actor_type: str = Field(..., description="Type of actor")
    summary: str = Field(..., description="Human-readable summary")
    detail: str | None = Field(None, description="Extended detail")
    metadata_json: str | None = Field(None, description="Raw JSON metadata")
    previous_hash: str | None = Field(None, description="Hash of the previous entry in the chain")
    entry_hash: str = Field(..., description="SHA-256 hash of this entry")
    timestamp: datetime = Field(..., description="When the event occurred")

    @property
    def parsed_metadata(self) -> dict[str, Any] | None:
        """Parse metadata_json to dict."""
        if self.metadata_json is None:
            return None
        import json
        return json.loads(self.metadata_json)


class AuditChainLink(BaseModel):
    """A single link in the chain verification result."""

    sequence: int
    id: str
    expected_hash: str
    stored_hash: str
    valid: bool


class AuditChainVerification(BaseModel):
    """Response for audit chain integrity verification."""

    valid: bool = Field(
        ..., description="Whether the entire chain is intact"
    )
    total_entries: int = Field(
        ..., description="Total number of audit entries verified"
    )
    invalid_entries: int = Field(
        0, description="Number of entries with broken chain links"
    )
    first_invalid_sequence: int | None = Field(
        None,
        description="Sequence number of the first invalid entry, if any",
    )
    checked_range: list[int] = Field(
        default_factory=list,
        description="[start_sequence, end_sequence] range that was verified",
    )
    details: list[AuditChainLink] = Field(
        default_factory=list,
        description="Per-entry verification details (only invalid entries unless verbose)",
    )
    suggestion: str | None = Field(
        None,
        description="Agent-friendly suggestion if chain is broken",
    )
