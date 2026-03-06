"""SQLAlchemy ORM models – central import point.

Import order matters: Base and mixins first, then domain models.
All models must be imported here so that ``Base.metadata`` knows about
every table when we run ``create_all`` or generate Alembic migrations.
"""

from app.models.base import (  # noqa: F401  – re-exported
    AuditMixin,
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.identity import (  # noqa: F401  – re-exported
    ApiKey,
    ApiKeyStatus,
    Organization,
    PlanTier,
    Role,
    RoleName,
    User,
)
from app.models.ingestion import (  # noqa: F401  – re-exported
    FileRecord,
    FileStatus,
    ParseResult,
)
from app.models.instrument import (  # noqa: F401  – re-exported
    Instrument,
    InstrumentDriver,
    WatchedFolder,
)
from app.models.data import (  # noqa: F401  – re-exported
    DataPoint,
    Dataset,
    Tag,
    TagAssociation,
)
from app.models.experiment import (  # noqa: F401  – re-exported
    EXPERIMENT_STATE_MACHINE,
    EXPERIMENT_TRANSITIONS,
    Experiment,
    ExperimentFile,
    ExperimentStatus,
)
from app.models.system import (  # noqa: F401  – re-exported
    AuditAction,
    AuditEvent,
    AuditLog,
    Notification,
    NotificationLevel,
    NotificationStatus,
    SystemConfig,
)

__all__ = [
    # Base & mixins
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "SoftDeleteMixin",
    "AuditMixin",
    # Identity
    "Organization",
    "User",
    "Role",
    "ApiKey",
    "PlanTier",
    "RoleName",
    "ApiKeyStatus",
    # Instrument
    "Instrument",
    "InstrumentDriver",
    "WatchedFolder",
    # Ingestion
    "FileRecord",
    "FileStatus",
    "ParseResult",
    # Data
    "DataPoint",
    "Dataset",
    "Tag",
    "TagAssociation",
    # Experiment
    "EXPERIMENT_STATE_MACHINE",
    "EXPERIMENT_TRANSITIONS",
    "Experiment",
    "ExperimentFile",
    "ExperimentStatus",
    # System & audit
    "AuditEvent",
    "AuditLog",
    "AuditAction",
    "Notification",
    "NotificationLevel",
    "NotificationStatus",
    "SystemConfig",
]
