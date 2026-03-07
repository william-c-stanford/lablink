"""Agents router — desktop agent registration, listing, and heartbeat.

Endpoints:
    POST /agents/               — Register a new desktop agent
    GET  /agents/               — List agents for the current organization
    GET  /agents/{id}           — Get an agent by ID
    POST /agents/{id}/heartbeat — Record a heartbeat from an agent
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError
from lablink.models.organization import Organization
from lablink.models.user import User
from lablink.models.agent import Agent
from lablink.schemas.agents import AgentCreate, AgentResponse, HeartbeatRequest
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# POST /agents/
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=Envelope[dict],
    status_code=201,
    operation_id="register_agent",
    response_model_exclude_none=True,
)
async def register_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Register a new desktop agent. Returns the agent record and a one-time API key."""
    raw_key = f"ll_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    agent = Agent(
        organization_id=org.id,
        name=body.name,
        platform=body.platform.value if body.platform else None,
        api_key_hash=key_hash,
        status="active",
    )
    db.add(agent)
    await db.flush()

    agent_resp = AgentResponse.model_validate(agent)
    return success_response(
        data={
            "agent": agent_resp.model_dump(mode="json"),
            "api_key": raw_key,
        }
    )


# ---------------------------------------------------------------------------
# GET /agents/
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=Envelope[list[AgentResponse]],
    operation_id="list_agents",
    response_model_exclude_none=True,
)
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List desktop agents for the current organization."""
    base = select(Agent).where(Agent.organization_id == org.id)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        base
        .order_by(Agent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    agents = [AgentResponse.model_validate(a) for a in result.scalars().all()]

    return success_response(
        data=agents,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /agents/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{agent_id}",
    response_model=Envelope[AgentResponse],
    operation_id="get_agent",
    response_model_exclude_none=True,
)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get a desktop agent by ID."""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.organization_id == org.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if agent is None:
        raise NotFoundError(
            message=f"Agent '{agent_id}' not found",
            suggestion="Use list_agents to find valid agent IDs.",
        )
    return success_response(data=AgentResponse.model_validate(agent))


# ---------------------------------------------------------------------------
# POST /agents/{id}/heartbeat
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/heartbeat",
    response_model=Envelope[AgentResponse],
    operation_id="record_agent_heartbeat",
    response_model_exclude_none=True,
)
async def record_heartbeat(
    agent_id: uuid.UUID,
    body: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Record a heartbeat from a desktop agent, updating its status and metadata."""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.organization_id == org.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if agent is None:
        raise NotFoundError(
            message=f"Agent '{agent_id}' not found",
            suggestion="Use list_agents to find valid agent IDs.",
        )

    agent.record_heartbeat()
    if body.version:
        agent.version = body.version
    if body.platform:
        agent.platform = body.platform.value

    await db.flush()
    return success_response(data=AgentResponse.model_validate(agent))
