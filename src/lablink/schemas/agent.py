"""Pydantic schemas for Desktop Agent CRUD and heartbeat operations.

Provides AgentCreate, AgentUpdate, AgentRead, AgentList, and
AgentHeartbeat with validation rules aligned to the agents SQL schema
from the roadmap.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentStatus(str, PyEnum):
    """Desktop agent lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    OFFLINE = "offline"


class AgentPlatform(str, PyEnum):
    """Operating system platforms for the Go desktop agent."""

    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    """Request body to register a new desktop agent.

    On successful registration the service returns the agent record along
    with a one-time API key that the caller must store securely.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable agent name, e.g. 'Lab-3 Workstation'",
    )
    platform: AgentPlatform | None = Field(
        None,
        description="Operating system: windows, macos, linux",
    )
    version: str | None = Field(
        None,
        max_length=50,
        description="Agent software version, e.g. '1.2.0'",
    )
    config: dict[str, Any] | None = Field(
        None,
        description="Agent configuration: watched_folders, instrument_hints, etc.",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Agent name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class AgentUpdate(BaseModel):
    """Request body to update agent fields (PATCH semantics).

    All fields are optional -- only provided fields are updated.
    Status changes (e.g. deactivation) are included here since agents
    don't have a separate state machine.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Agent display name",
    )
    platform: AgentPlatform | None = Field(
        None,
        description="Operating system platform",
    )
    version: str | None = Field(
        None,
        max_length=50,
        description="Agent software version",
    )
    status: AgentStatus | None = Field(
        None,
        description="Agent status: active, inactive, offline",
    )
    config: dict[str, Any] | None = Field(
        None,
        description="Agent configuration (replaces existing config entirely)",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        """Ensure name is not just whitespace when provided."""
        if v is not None:
            if not v.strip():
                raise ValueError("Agent name must not be blank")
            return v.strip()
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> AgentUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class AgentRead(BaseModel):
    """Full agent representation returned by API endpoints.

    Includes computed ``is_online`` based on ``last_heartbeat_at`` and
    current status, enabling consuming agents to assess availability.
    """

    id: str
    org_id: str | None = Field(None, description="Organization ID")
    name: str
    platform: str | None = None
    version: str | None = None
    status: AgentStatus = AgentStatus.ACTIVE
    last_heartbeat_at: datetime | None = None
    config: dict[str, Any] | None = None
    is_online: bool = Field(
        default=False,
        description="Whether the agent is considered online (status=active and recent heartbeat)",
    )

    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, data: Any) -> Any:
        """Handle ORM objects and compute is_online."""
        if hasattr(data, "__dict__"):
            d: dict[str, Any] = {}
            for key in (
                "id", "org_id", "organization_id", "name", "platform",
                "version", "status", "last_heartbeat_at", "config_json",
                "config", "api_key_hash", "created_at", "updated_at",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    d[key] = val
            # Normalize org_id
            if "org_id" not in d or d.get("org_id") is None:
                d["org_id"] = d.pop("organization_id", None)
            data = d

        # Map config_json -> config
        if isinstance(data, dict):
            import json

            config_raw = data.pop("config_json", None)
            if config_raw and isinstance(config_raw, str):
                try:
                    data["config"] = json.loads(config_raw)
                except (ValueError, TypeError):
                    data["config"] = None
            elif config_raw and isinstance(config_raw, dict):
                data["config"] = config_raw

            # Compute is_online: active status + heartbeat within 3 minutes
            status_val = data.get("status")
            heartbeat_raw = data.get("last_heartbeat_at")
            if status_val and heartbeat_raw:
                from datetime import timezone

                try:
                    status_enum = (
                        AgentStatus(status_val)
                        if not isinstance(status_val, AgentStatus)
                        else status_val
                    )
                    # Parse heartbeat if it's a string
                    if isinstance(heartbeat_raw, str):
                        heartbeat = datetime.fromisoformat(heartbeat_raw)
                    else:
                        heartbeat = heartbeat_raw
                    now = datetime.now(timezone.utc)
                    # Ensure heartbeat is timezone-aware
                    if heartbeat.tzinfo is None:
                        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
                    delta = (now - heartbeat).total_seconds()
                    # Online if active and heartbeat within 3 minutes (180s)
                    data["is_online"] = (
                        status_enum == AgentStatus.ACTIVE and delta < 180
                    )
                except (ValueError, TypeError):
                    data["is_online"] = False
            else:
                data["is_online"] = False

            # Strip sensitive api_key_hash from read responses
            data.pop("api_key_hash", None)

        return data


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class AgentHeartbeat(BaseModel):
    """Payload sent by the desktop agent on its periodic heartbeat.

    The agent sends system info so the cloud can track health and
    version compliance.
    """

    version: str | None = Field(
        None,
        max_length=50,
        description="Current agent software version",
    )
    platform: AgentPlatform | None = Field(
        None,
        description="Current OS platform",
    )
    hostname: str | None = Field(
        None,
        max_length=255,
        description="Machine hostname",
    )
    cpu_percent: float | None = Field(
        None,
        ge=0,
        le=100,
        description="Current CPU utilization percentage",
    )
    memory_percent: float | None = Field(
        None,
        ge=0,
        le=100,
        description="Current memory utilization percentage",
    )
    disk_free_bytes: int | None = Field(
        None,
        ge=0,
        description="Free disk space in bytes on the watched volume",
    )
    queue_depth: int | None = Field(
        None,
        ge=0,
        description="Number of files currently queued for upload",
    )
    uptime_seconds: int | None = Field(
        None,
        ge=0,
        description="Agent process uptime in seconds",
    )


# ---------------------------------------------------------------------------
# Registration response (includes one-time API key)
# ---------------------------------------------------------------------------


class AgentRegistered(BaseModel):
    """Response returned after successful agent registration.

    Contains the agent record plus a one-time plaintext API key that
    the caller must store securely. The server only stores the hash.
    """

    agent: AgentRead
    api_key: str = Field(
        ...,
        description="One-time plaintext API key. Store securely; it cannot be retrieved again.",
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class AgentList(BaseModel):
    """Paginated list of agents."""

    items: list[AgentRead]
    total: int
    page: int
    page_size: int
