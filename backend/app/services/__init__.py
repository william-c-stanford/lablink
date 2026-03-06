"""Service layer — fat services, thin routers."""

from app.services.audit import (  # noqa: F401
    ChainVerificationResult,
    compute_entry_hash,
    create_audit_event,
    count_audit_entries,
    get_audit_log,
    verify_chain,
)
from app.services.auth import (  # noqa: F401
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_current_user_from_token,
    get_user_by_id,
    login_user,
    register_user,
)
from app.services.experiment import (  # noqa: F401
    create_experiment,
    get_experiment,
    list_experiments,
    soft_delete_experiment,
    transition_experiment,
    update_experiment,
)
from app.services.storage import (  # noqa: F401
    FileStorageService,
    LocalStorageBackend,
    StorageResult,
    create_storage_service,
)

__all__ = [
    # Audit
    "ChainVerificationResult",
    "compute_entry_hash",
    "create_audit_event",
    "count_audit_entries",
    "get_audit_log",
    "verify_chain",
    # Auth
    "authenticate_user",
    "create_access_token",
    "decode_access_token",
    "get_current_user_from_token",
    "get_user_by_id",
    "login_user",
    "register_user",
    # Experiment
    "create_experiment",
    "get_experiment",
    "list_experiments",
    "update_experiment",
    "soft_delete_experiment",
    "transition_experiment",
    # Storage
    "FileStorageService",
    "LocalStorageBackend",
    "StorageResult",
    "create_storage_service",
]
