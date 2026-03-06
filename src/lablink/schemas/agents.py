"""Pydantic schemas for Desktop Agent registration, responses, and heartbeat.

Provides AgentCreate, AgentResponse, and HeartbeatRequest aligned to the
Agent ORM model in lablink.models.lab.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lablink.schemas.agent import AgentPlatform, AgentStatus


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    """Request body to register a new desktop agent."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable agent name, e.g. 'Lab-3 Workstation'",
    )
    platform: AgentPlatform | None = Field(
        default=None,
        description="Operating system: windows, macos, linux",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class AgentResponse(BaseModel):
    """Full agent representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    platform: str | None = Field(None, description="Operating system platform")
    version: str | None = Field(None, description="Agent software version")
    status: str = Field(..., description="Agent status: active, inactive, offline")
    last_heartbeat_at: datetime | None = Field(None, description="Timestamp of last heartbeat")
    created_at: datetime = Field(..., description="Agent registration timestamp")


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    """Payload sent by the desktop agent on its periodic heartbeat."""

    version: str | None = Field(
        default=None,
        max_length=50,
        description="Current agent software version",
    )
    platform: AgentPlatform | None = Field(
        default=None,
        description="Current OS platform",
    )
    system_info: dict[str, Any] | None = Field(
        default=None,
        description="System telemetry: cpu_percent, memory_percent, disk_free_bytes, hostname, etc.",
    )
