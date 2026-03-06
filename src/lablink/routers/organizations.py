"""Organizations router — CRUD and membership management.

Endpoints:
    POST   /organizations/                      — Create a new organization
    GET    /organizations/{id}                   — Get organization by ID
    PATCH  /organizations/{id}                   — Update organization
    GET    /organizations/{id}/members           — List organization members
    POST   /organizations/{id}/members           — Add a member
    PATCH  /organizations/{id}/members/{user_id} — Update member role
    DELETE /organizations/{id}/members/{user_id} — Remove a member
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db, require_role
from lablink.exceptions import NotFoundError
from lablink.models import Organization, User
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.schemas.organization import (
    AddMemberRequest,
    MembershipRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from lablink.services.organization_service import (
    add_member,
    create_organization,
    get_organization,
    list_members,
    remove_member,
    update_member_role,
    update_organization,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ---------------------------------------------------------------------------
# POST /organizations/
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=Envelope[OrganizationRead],
    status_code=201,
    operation_id="create_organization",
    response_model_exclude_none=True,
)
async def create_org(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Envelope:
    """Create a new organization with the current user as admin."""
    org = await create_organization(db, body, created_by_user_id=user.id)
    return success_response(data=org)


# ---------------------------------------------------------------------------
# GET /organizations/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{org_id}",
    response_model=Envelope[OrganizationRead],
    operation_id="get_organization",
    response_model_exclude_none=True,
)
async def get_org(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Envelope:
    """Get an organization by ID."""
    org = await get_organization(db, org_id)
    if org is None:
        raise NotFoundError(
            message=f"Organization '{org_id}' not found",
            suggestion="Use list_organizations to find valid organization IDs.",
        )
    return success_response(data=org)


# ---------------------------------------------------------------------------
# PATCH /organizations/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{org_id}",
    response_model=Envelope[OrganizationRead],
    operation_id="update_organization",
    response_model_exclude_none=True,
)
async def update_org(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> Envelope:
    """Update an organization (admin only)."""
    org = await update_organization(db, org_id, body)
    return success_response(data=org)


# ---------------------------------------------------------------------------
# GET /organizations/{id}/members
# ---------------------------------------------------------------------------


@router.get(
    "/{org_id}/members",
    response_model=Envelope[list[MembershipRead]],
    operation_id="list_organization_members",
    response_model_exclude_none=True,
)
async def list_org_members(
    org_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Envelope:
    """List all members of an organization."""
    members, total = await list_members(db, org_id, page=page, page_size=page_size)
    return success_response(
        data=members,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# POST /organizations/{id}/members
# ---------------------------------------------------------------------------


@router.post(
    "/{org_id}/members",
    response_model=Envelope[MembershipRead],
    status_code=201,
    operation_id="add_organization_member",
    response_model_exclude_none=True,
)
async def add_org_member(
    org_id: uuid.UUID,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> Envelope:
    """Add a member to an organization (admin only)."""
    membership = await add_member(
        db,
        organization_id=org_id,
        user_id=body.user_id,
        role=body.role.value,
    )
    return success_response(data=membership)


# ---------------------------------------------------------------------------
# PATCH /organizations/{id}/members/{user_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{org_id}/members/{member_user_id}",
    response_model=Envelope[MembershipRead],
    operation_id="update_organization_member_role",
    response_model_exclude_none=True,
)
async def update_org_member_role(
    org_id: uuid.UUID,
    member_user_id: uuid.UUID,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> Envelope:
    """Update a member's role within an organization (admin only)."""
    membership = await update_member_role(
        db,
        organization_id=org_id,
        user_id=member_user_id,
        new_role=body.role.value,
    )
    return success_response(data=membership)


# ---------------------------------------------------------------------------
# DELETE /organizations/{id}/members/{user_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{org_id}/members/{member_user_id}",
    response_model=Envelope[dict],
    operation_id="remove_organization_member",
    response_model_exclude_none=True,
)
async def remove_org_member(
    org_id: uuid.UUID,
    member_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> Envelope:
    """Remove a member from an organization (admin only)."""
    await remove_member(db, organization_id=org_id, user_id=member_user_id)
    return success_response(data={"removed": True})
