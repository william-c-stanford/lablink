"""Projects router — CRUD for project resources.

Endpoints:
    POST  /projects/     — Create a new project
    GET   /projects/     — List projects for the current organization
    GET   /projects/{id} — Get a project by ID
    PATCH /projects/{id} — Update a project
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError
from lablink.models import Organization, User
from lablink.models import Project
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.schemas.projects import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# POST /projects/
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=Envelope[ProjectResponse],
    status_code=201,
    operation_id="create_project",
    response_model_exclude_none=True,
)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Create a new project within the current organization."""
    project = Project(
        organization_id=org.id,
        name=body.name,
        description=body.description,
        created_by=user.id,
    )
    db.add(project)
    await db.flush()
    return success_response(data=ProjectResponse.model_validate(project))


# ---------------------------------------------------------------------------
# GET /projects/
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=Envelope[list[ProjectResponse]],
    operation_id="list_projects",
    response_model_exclude_none=True,
)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List projects for the current organization."""
    base = select(Project).where(
        Project.organization_id == org.id,
        Project.archived_at.is_(None),
    )
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        base
        .order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    projects = [ProjectResponse.model_validate(p) for p in result.scalars().all()]

    return success_response(
        data=projects,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /projects/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}",
    response_model=Envelope[ProjectResponse],
    operation_id="get_project",
    response_model_exclude_none=True,
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get a project by ID."""
    stmt = select(Project).where(
        Project.id == project_id,
        Project.organization_id == org.id,
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        raise NotFoundError(
            message=f"Project '{project_id}' not found",
            suggestion="Use list_projects to find valid project IDs.",
        )
    return success_response(data=ProjectResponse.model_validate(project))


# ---------------------------------------------------------------------------
# PATCH /projects/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{project_id}",
    response_model=Envelope[ProjectResponse],
    operation_id="update_project",
    response_model_exclude_none=True,
)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Update a project's fields (PATCH semantics)."""
    stmt = select(Project).where(
        Project.id == project_id,
        Project.organization_id == org.id,
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        raise NotFoundError(
            message=f"Project '{project_id}' not found",
            suggestion="Use list_projects to find valid project IDs.",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    return success_response(data=ProjectResponse.model_validate(project))
