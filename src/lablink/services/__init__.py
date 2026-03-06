"""LabLink service layer — business logic with zero HTTP awareness."""

# Graceful imports — modules may not exist yet during incremental builds
try:
    from lablink.services.auth_service import (
        authenticate_user,
        check_permission,
        create_access_token,
        decode_access_token,
        get_current_user_from_token,
        get_user_by_id,
        hash_password,
        login_user,
        register_user,
        validate_api_token,
        verify_password,
    )
except ImportError:
    pass

try:
    from lablink.services.organization_service import (
        add_member,
        create_organization,
        get_membership,
        get_organization,
        get_organization_by_slug,
        list_members,
        list_organizations,
        remove_member,
        soft_delete_organization,
        update_member_role,
        update_organization,
    )
except ImportError:
    pass

try:
    from lablink.services.audit_service import (
        compute_event_hash,
        count_audit_events,
        create_audit_event,
        create_audit_event_from_schema,
        get_audit_event_by_id,
        list_audit_events,
        verify_audit_chain,
    )
except ImportError:
    pass

try:
    from lablink.services.export_service import (
        ExportFormat,
        ExportJob,
        ExportRequest,
        ExportService,
        ExportStatus,
    )
except ImportError:
    pass

try:
    from lablink.services.webhook_service import (
        WebhookService,
        generate_secret,
        sign_payload,
        verify_signature,
    )
except ImportError:
    pass

from lablink.services.campaign_service import (
    CampaignProgress,
    add_experiment_to_campaign,
    create_campaign,
    get_campaign,
    get_campaign_progress,
    list_campaign_experiments,
    list_campaigns,
    remove_experiment_from_campaign,
    transition_campaign,
    update_campaign,
)
from lablink.services.experiment_service import (
    add_predecessor,
    create_experiment,
    get_experiment,
    link_upload,
    list_experiments,
    soft_delete_experiment,
    transition_experiment,
    unlink_upload,
    update_experiment,
)
from lablink.services.search_service import (
    SearchResult,
    SearchService,
    get_search_service,
    reset_search_service,
)

__all__ = [
    # Experiment service
    "create_experiment",
    "get_experiment",
    "list_experiments",
    "update_experiment",
    "soft_delete_experiment",
    "transition_experiment",
    "link_upload",
    "unlink_upload",
    "add_predecessor",
    # Campaign service
    "create_campaign",
    "get_campaign",
    "list_campaigns",
    "update_campaign",
    "transition_campaign",
    "get_campaign_progress",
    "add_experiment_to_campaign",
    "remove_experiment_from_campaign",
    "list_campaign_experiments",
    "CampaignProgress",
    # Search service
    "SearchService",
    "SearchResult",
    "get_search_service",
    "reset_search_service",
]
