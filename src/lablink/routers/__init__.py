"""LabLink API routers — thin HTTP wrappers around the service layer.

Each router module defines an ``APIRouter`` instance named ``router``
that is registered in ``lablink.main._register_routers``.
"""

from lablink.routers.admin import router as admin_router
from lablink.routers.agents import router as agents_router
from lablink.routers.audit import router as audit_router
from lablink.routers.auth import router as auth_router
from lablink.routers.campaigns import router as campaigns_router
from lablink.routers.data import router as data_router
from lablink.routers.experiments import router as experiments_router
from lablink.routers.instruments import router as instruments_router
from lablink.routers.organizations import router as organizations_router
from lablink.routers.projects import router as projects_router
from lablink.routers.uploads import router as uploads_router
from lablink.routers.webhooks import router as webhooks_router

__all__ = [
    "admin_router",
    "agents_router",
    "audit_router",
    "auth_router",
    "campaigns_router",
    "data_router",
    "experiments_router",
    "instruments_router",
    "organizations_router",
    "projects_router",
    "uploads_router",
    "webhooks_router",
]
