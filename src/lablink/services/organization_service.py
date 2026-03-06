"""Organization service: tenant CRUD, membership management.

All business logic for managing organizations and their members.
Zero HTTP awareness -- routers call these functions and wrap results
in Envelope responses.

Public API:
    - create_organization -- create a new org
    - get_organization / get_organization_by_slug -- lookups
    - list_organizations -- paginated list
    - update_organization -- partial update
    - soft_delete_organization -- soft delete with 90-day retention
    - add_member / remove_member / update_member_role -- membership management
    - list_members -- list org members
    - get_membership -- get a specific membership
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.exceptions import (
    ConflictError,
    DuplicateError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from lablink.models import (
    MemberRole,
    Membership,
    Organization,
    Tier,
    User,
)
from lablink.schemas.organization import (
    MembershipRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


async def create_organization(
    session: AsyncSession,
    data: OrganizationCreate,
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> OrganizationRead:
    """Create a new organization.

    If ``created_by_user_id`` is provided, an admin membership is
    automatically created for that user.

    Raises:
        DuplicateError: If the slug is already taken.
    """
    # Check slug uniqueness
    existing = await session.execute(
        select(Organization).where(Organization.slug == data.slug)
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateError(
            message=f"Organization with slug '{data.slug}' already exists",
            suggestion="Choose a different slug or use the existing organization.",
            field="slug",
        )

    org = Organization(
        name=data.name,
        slug=data.slug,
        tier=data.tier.value if isinstance(data.tier, Tier) else data.tier,
    )
    session.add(org)
    await session.flush()

    # Auto-create admin membership for the creating user
    if created_by_user_id is not None:
        membership = Membership(
            user_id=created_by_user_id,
            organization_id=org.id,
            role=MemberRole.admin.value,
        )
        session.add(membership)
        await session.flush()

    return OrganizationRead.model_validate(org)


async def get_organization(
    session: AsyncSession, org_id: uuid.UUID
) -> OrganizationRead | None:
    """Fetch an organization by ID, returning None if not found or deleted."""
    result = await session.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        return None
    return OrganizationRead.model_validate(org)


async def get_organization_by_slug(
    session: AsyncSession, slug: str
) -> OrganizationRead | None:
    """Fetch an organization by slug."""
    result = await session.execute(
        select(Organization).where(
            Organization.slug == slug,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        return None
    return OrganizationRead.model_validate(org)


async def list_organizations(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    user_id: uuid.UUID | None = None,
) -> tuple[list[OrganizationRead], int]:
    """List organizations with pagination.

    If ``user_id`` is provided, only returns orgs the user is a member of.

    Returns:
        Tuple of (organizations, total_count).
    """
    base_query = select(Organization).where(Organization.deleted_at.is_(None))
    count_query = select(func.count(Organization.id)).where(
        Organization.deleted_at.is_(None)
    )

    if user_id is not None:
        base_query = base_query.join(
            Membership, Membership.organization_id == Organization.id
        ).where(Membership.user_id == user_id)
        count_query = count_query.join(
            Membership, Membership.organization_id == Organization.id
        ).where(Membership.user_id == user_id)

    # Get total count
    total = (await session.execute(count_query)).scalar_one()

    # Get page
    offset = (page - 1) * page_size
    stmt = (
        base_query
        .order_by(Organization.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    orgs = [OrganizationRead.model_validate(o) for o in result.scalars().all()]

    return orgs, total


async def update_organization(
    session: AsyncSession,
    org_id: uuid.UUID,
    data: OrganizationUpdate,
) -> OrganizationRead:
    """Update organization fields (PATCH semantics).

    Raises:
        NotFoundError: If the organization doesn't exist.
        DuplicateError: If the new slug conflicts with another org.
    """
    result = await session.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            message=f"Organization '{org_id}' not found",
            suggestion="Use list_organizations to find valid organization IDs.",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Check slug uniqueness if being changed
    if "slug" in update_data and update_data["slug"] != org.slug:
        existing = await session.execute(
            select(Organization).where(
                Organization.slug == update_data["slug"],
                Organization.id != org_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise DuplicateError(
                message=f"Slug '{update_data['slug']}' is already taken",
                suggestion="Choose a different slug.",
                field="slug",
            )

    # Apply updates
    for field, value in update_data.items():
        if field == "tier" and isinstance(value, Tier):
            value = value.value
        setattr(org, field, value)

    await session.flush()
    return OrganizationRead.model_validate(org)


async def soft_delete_organization(
    session: AsyncSession, org_id: uuid.UUID
) -> None:
    """Soft-delete an organization (90-day retention before hard delete).

    Raises:
        NotFoundError: If the organization doesn't exist.
    """
    result = await session.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            message=f"Organization '{org_id}' not found",
            suggestion="Use list_organizations to find valid organization IDs.",
        )

    org.deleted_at = datetime.now(timezone.utc)
    await session.flush()


# ---------------------------------------------------------------------------
# Membership management
# ---------------------------------------------------------------------------


async def add_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = MemberRole.scientist.value,
) -> MembershipRead:
    """Add a user to an organization with the specified role.

    Raises:
        NotFoundError: If the organization or user doesn't exist.
        DuplicateError: If the user is already a member.
        ValidationError: If the org has reached its user limit.
    """
    # Verify org exists
    org_result = await session.execute(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise NotFoundError(
            message=f"Organization '{organization_id}' not found",
            suggestion="Use list_organizations to find valid organization IDs.",
        )

    # Verify user exists
    user_result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise NotFoundError(
            message=f"User '{user_id}' not found",
            suggestion="Use list_users to find valid user IDs.",
        )

    # Check for existing membership
    existing = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateError(
            message="User is already a member of this organization",
            suggestion="Use update_member_role to change the user's role instead.",
        )

    # Check user limit
    member_count = (
        await session.execute(
            select(func.count(Membership.id)).where(
                Membership.organization_id == organization_id
            )
        )
    ).scalar_one()
    if member_count >= org.user_limit:
        raise ValidationError(
            message=f"Organization has reached its user limit ({org.user_limit})",
            suggestion="Upgrade the organization's plan to add more users.",
        )

    membership = Membership(
        user_id=user_id,
        organization_id=organization_id,
        role=role,
    )
    session.add(membership)
    await session.flush()

    return MembershipRead.model_validate(membership)


async def remove_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Remove a user from an organization.

    Raises:
        NotFoundError: If the membership doesn't exist.
        ValidationError: If trying to remove the last admin.
    """
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError(
            message="Membership not found",
            suggestion="Check the user_id and organization_id.",
        )

    # Prevent removing the last admin
    if membership.role == MemberRole.admin.value:
        admin_count = (
            await session.execute(
                select(func.count(Membership.id)).where(
                    Membership.organization_id == organization_id,
                    Membership.role == MemberRole.admin.value,
                )
            )
        ).scalar_one()
        if admin_count <= 1:
            raise ValidationError(
                message="Cannot remove the last admin from an organization",
                suggestion="Promote another member to admin before removing this one.",
            )

    await session.delete(membership)
    await session.flush()


async def update_member_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    new_role: str,
) -> MembershipRead:
    """Update a member's role within an organization.

    Raises:
        NotFoundError: If the membership doesn't exist.
        ValidationError: If demoting the last admin.
    """
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError(
            message="Membership not found",
            suggestion="Check the user_id and organization_id.",
        )

    # Prevent demoting the last admin
    if (
        membership.role == MemberRole.admin.value
        and new_role != MemberRole.admin.value
    ):
        admin_count = (
            await session.execute(
                select(func.count(Membership.id)).where(
                    Membership.organization_id == organization_id,
                    Membership.role == MemberRole.admin.value,
                )
            )
        ).scalar_one()
        if admin_count <= 1:
            raise ValidationError(
                message="Cannot demote the last admin",
                suggestion="Promote another member to admin first.",
            )

    membership.role = new_role
    await session.flush()

    return MembershipRead.model_validate(membership)


async def list_members(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[MembershipRead], int]:
    """List all members of an organization with pagination.

    Returns:
        Tuple of (memberships, total_count).
    """
    count_query = select(func.count(Membership.id)).where(
        Membership.organization_id == organization_id
    )
    total = (await session.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        select(Membership)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    members = [MembershipRead.model_validate(m) for m in result.scalars().all()]

    return members, total


async def get_membership(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> MembershipRead | None:
    """Get a specific membership record."""
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return None
    return MembershipRead.model_validate(membership)
