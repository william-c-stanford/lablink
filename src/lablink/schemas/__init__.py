"""LabLink schema exports.

This module re-exports key Pydantic schemas for convenient imports.
Detailed internal schemas (agent.py, instrument.py, organization.py) coexist
with the router-facing schemas (agents.py, instruments.py, organizations.py).
Import from the specific sub-module when you need to disambiguate.
"""

# -- Canonical parsed data --------------------------------------------------
from lablink.schemas.canonical import InstrumentSettings, MeasurementValue, ParsedResult

# -- Response envelope ------------------------------------------------------
from lablink.schemas.envelope import Envelope, ErrorDetail, PaginationMeta, ResponseMeta

# -- Auth -------------------------------------------------------------------
from lablink.schemas.auth import (
    ApiTokenCreate,
    ApiTokenResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

# -- Organizations ----------------------------------------------------------
from lablink.schemas.organizations import (
    InviteMemberRequest,
    MemberResponse,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    UpdateMemberRoleRequest,
)

# -- Projects ---------------------------------------------------------------
from lablink.schemas.projects import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)

# -- Instruments (router-facing) --------------------------------------------
from lablink.schemas.instruments import (
    InstrumentResponse,
)

# -- Instruments (detailed, legacy) -----------------------------------------
from lablink.schemas.instrument import (
    InstrumentCreate,
    InstrumentList,
    InstrumentRead,
    InstrumentType,
    InstrumentUpdate,
)

# -- Agents (router-facing) ------------------------------------------------
from lablink.schemas.agents import (
    AgentResponse,
    HeartbeatRequest,
)

# -- Agents (detailed, legacy) ---------------------------------------------
from lablink.schemas.agent import (
    AgentCreate,
    AgentHeartbeat,
    AgentList,
    AgentPlatform,
    AgentRead,
    AgentRegistered,
    AgentStatus,
    AgentUpdate,
)

# -- Uploads ----------------------------------------------------------------
from lablink.schemas.uploads import (
    UploadListParams,
    UploadResponse,
)

# -- Experiments ------------------------------------------------------------
from lablink.schemas.experiments import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
    LinkUploadRequest,
    OutcomeRequest,
)

# -- Campaigns --------------------------------------------------------------
from lablink.schemas.campaigns import (
    CampaignCreate,
    CampaignProgressResponse,
    CampaignResponse,
)

# -- Webhooks ---------------------------------------------------------------
from lablink.schemas.webhooks import (
    WebhookCreate,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookUpdate,
)

# -- Audit ------------------------------------------------------------------
from lablink.schemas.audit import (
    AuditChainLink,
    AuditChainVerification,
    AuditEventCreate,
    AuditEventRead,
    AuditEventResponse,
    AuditListParams,
)

__all__ = [
    # Canonical
    "MeasurementValue",
    "InstrumentSettings",
    "ParsedResult",
    # Envelope
    "Envelope",
    "ErrorDetail",
    "PaginationMeta",
    "ResponseMeta",
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "ApiTokenCreate",
    "ApiTokenResponse",
    "UserResponse",
    # Organizations
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "MemberResponse",
    "InviteMemberRequest",
    "UpdateMemberRoleRequest",
    # Projects
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    # Instruments
    "InstrumentCreate",
    "InstrumentUpdate",
    "InstrumentList",
    "InstrumentRead",
    "InstrumentResponse",
    "InstrumentType",
    # Agents
    "AgentCreate",
    "AgentUpdate",
    "AgentHeartbeat",
    "AgentList",
    "AgentPlatform",
    "AgentRead",
    "AgentRegistered",
    "AgentStatus",
    "AgentResponse",
    "HeartbeatRequest",
    # Uploads
    "UploadResponse",
    "UploadListParams",
    # Experiments
    "ExperimentCreate",
    "ExperimentUpdate",
    "ExperimentResponse",
    "OutcomeRequest",
    "LinkUploadRequest",
    # Campaigns
    "CampaignCreate",
    "CampaignResponse",
    "CampaignProgressResponse",
    # Webhooks
    "WebhookCreate",
    "WebhookUpdate",
    "WebhookResponse",
    "WebhookDeliveryResponse",
    # Audit
    "AuditEventCreate",
    "AuditEventRead",
    "AuditEventResponse",
    "AuditListParams",
    "AuditChainLink",
    "AuditChainVerification",
]
