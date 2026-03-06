"""SQLAlchemy ORM models for LabLink.

Re-exports all 16 domain models, enums, mixins, and transition maps
so consumers can do::

    from lablink.models import Organization, Upload, AuditEvent, ...

Importing this module registers every model with ``Base.metadata``,
which is required for ``create_all()`` and Alembic auto-generation.

Model count by file:
- organization.py       : Organization                          (1)
- user.py               : User                                  (1)
- membership.py         : Membership                            (1)
- project.py            : Project                               (1)
- instrument.py         : Instrument                            (1)
- agent.py              : Agent                                 (1)
- upload.py             : Upload                                (1)
- parsed_data.py        : ParsedData                            (1)
- experiment.py         : Experiment                            (1)
- experiment_upload.py  : ExperimentUpload                      (1)
- campaign.py           : Campaign                              (1)
- api_token.py          : ApiToken                              (1)
- audit_event.py        : AuditEvent                            (1)
- webhook.py            : Webhook                               (1)
- webhook_delivery.py   : WebhookDelivery                       (1)
                                                       Total = 16*

* ExperimentUpload is a composite-PK association table, counted as a model.
"""

from lablink.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin
from lablink.models.organization import Organization, Tier
from lablink.models.user import User
from lablink.models.membership import Membership, MemberRole
from lablink.models.project import Project
from lablink.models.instrument import Instrument
from lablink.models.agent import Agent
from lablink.models.upload import Upload, UploadStatus
from lablink.models.parsed_data import ParsedData
from lablink.models.campaign import Campaign, CampaignStatus, CAMPAIGN_TRANSITIONS
from lablink.models.experiment import (
    Experiment,
    ExperimentStatus,
    EXPERIMENT_TRANSITIONS,
)
from lablink.models.experiment_upload import ExperimentUpload
from lablink.models.api_token import ApiToken, IdentityType, TokenScope
from lablink.models.audit_event import AuditEvent
from lablink.models.webhook import Webhook
from lablink.models.webhook_delivery import DeliveryStatus, WebhookDelivery

__all__ = [
    # Base & mixins
    "Base",
    "TimestampMixin",
    "UpdatedAtMixin",
    "SoftDeleteMixin",
    # Organization & identity
    "Organization",
    "Tier",
    "User",
    "Membership",
    "MemberRole",
    "ApiToken",
    "TokenScope",
    "IdentityType",
    # Lab infrastructure
    "Project",
    "Instrument",
    "Agent",
    # Data pipeline
    "Upload",
    "UploadStatus",
    "ParsedData",
    # Experiments & campaigns
    "Experiment",
    "ExperimentStatus",
    "EXPERIMENT_TRANSITIONS",
    "ExperimentUpload",
    "Campaign",
    "CampaignStatus",
    "CAMPAIGN_TRANSITIONS",
    # Audit & integrations
    "AuditEvent",
    "Webhook",
    "WebhookDelivery",
    "DeliveryStatus",
]
