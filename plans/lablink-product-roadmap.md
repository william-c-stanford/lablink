# LabLink: 2-Year Product Roadmap & MVP Implementation Spec

## Vision

LabLink is the agent-native data integration layer for research laboratories. It starts as a self-service instrument connectivity platform for mid-market labs, and evolves into the foundational data backbone for closed-loop self-driving laboratories (SDLs). Every architectural decision from day one serves both the immediate product (connect instruments, stop manual data entry) and the long-term platform (be the tool layer that AI agents use to close the DMTA loop).

**Positioning:** "The AI-ready data layer for autonomous labs. Connect instruments today, close the loop tomorrow."

---

## Architecture Overview

```
                    LAB NETWORK                              CLOUD PLATFORM
    ┌──────────────────────────────────┐     ┌──────────────────────────────────────────────┐
    │                                  │     │                                              │
    │  ┌──────────┐  ┌──────────┐    │     │  ┌──────────────┐   ┌──────────────────┐     │
    │  │Instrument│  │Instrument│    │     │  │  Ingestion    │   │  MCP Server      │     │
    │  │  PC #1   │  │  PC #2   │    │     │  │  Service      │   │  (FastMCP)       │     │
    │  └────┬─────┘  └────┬─────┘    │     │  │  (FastAPI)    │   │  Curated Toolsets│     │
    │       │              │          │     │  └──────┬───────┘   └────────┬─────────┘     │
    │  ┌────▼──────────────▼───────┐  │     │         │                    │               │
    │  │     LabLink Agent (Go)    │  │     │  ┌──────▼────────────────────▼─────────┐     │
    │  │  - fsnotify file watcher  │  │     │  │          FastAPI Application         │     │
    │  │  - BBolt local queue      │  │     │  │  - REST API (OpenAPI 3.1)           │     │
    │  │  - Store & forward        │  │     │  │  - Webhook dispatch                 │     │
    │  │  - HTTPS outbound only    │  │     │  │  - { data, meta, errors } envelope  │     │
    │  │  - Proxy support          │  │     │  └──────┬───────────────────────────────┘     │
    │  └────────┬──────────────────┘  │     │         │                                     │
    │           │ HTTPS POST          │     │  ┌──────▼──────────┐  ┌──────────────────┐   │
    └───────────┼─────────────────────┘     │  │  Parser Engine  │  │  Celery Workers  │   │
                │                            │  │  (Plugin arch)  │  │  - Parse tasks   │   │
                └───────────────────────────▶│  │  - allotropy    │  │  - Webhook fire  │   │
                                             │  │  - Custom CSV   │  │  - Index sync    │   │
                                             │  └──────┬──────────┘  └──────────────────┘   │
                                             │         │                                     │
                                             │  ┌──────▼──────────────────────────────────┐ │
                                             │  │  PostgreSQL    S3         Elasticsearch  │ │
                                             │  │  (metadata,    (raw       (full-text     │ │
                                             │  │   audit trail,  files)     search index) │ │
                                             │  │   experiments)                           │ │
                                             │  └──────┬──────────────────────────────────┘ │
                                             │         │                                     │
                                             │  ┌──────▼──────────────────────────────────┐ │
                                             │  │  React Dashboard + Plotly.js             │ │
                                             │  │  (Human interface — every action also    │ │
                                             │  │   available via API for agent parity)    │ │
                                             │  └─────────────────────────────────────────┘ │
                                             └──────────────────────────────────────────────┘
```

---

## State Machines

### Upload Lifecycle

```
                 ┌──────────────┐
                 │ file_detected │
                 └──────┬───────┘
                        │ (stability check: 5s no writes)
                 ┌──────▼───────┐
                 │ queued_local  │
                 └──────┬───────┘
                        │ (HTTPS POST)
              ┌─────────▼──────────┐
              │     uploading      │
              └──┬─────────────┬───┘
                 │             │
          ┌──────▼──────┐  ┌──▼───────────┐
          │  uploaded    │  │ upload_failed │──(retry 3x w/ backoff)──┐
          └──────┬──────┘  └──────────────┘                          │
                 │                    ▲                                │
          ┌──────▼──────┐            └────────────────────────────────┘
          │   parsing   │
          └──┬──────┬───┘
             │      │
      ┌──────▼──┐ ┌─▼────────────┐
      │ parsed  │ │ parse_failed  │──(raw file preserved in S3)
      └────┬────┘ └──────────────┘
           │
      ┌────▼────┐
      │ indexed │  (Elasticsearch sync — async, eventually consistent)
      └─────────┘
```

### Experiment Lifecycle

```
      ┌─────────┐
      │ planned │──────────────────────┐
      └────┬────┘                      │
           │ (execution starts)        │ (cancelled before start)
      ┌────▼────┐                 ┌────▼─────┐
      │ running │                 │ cancelled │
      └──┬───┬──┘                 └──────────┘
         │   │
  ┌──────▼┐ ┌▼───────┐
  │completed││ failed │
  └────────┘└────────┘
```

**Transitions:** Human or agent can trigger any valid transition via API. The audit trail records who/what triggered each transition and when.

---

## Data Model (Core Schemas)

### PostgreSQL Schema

```sql
-- Organizations (tenants)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    tier VARCHAR(20) NOT NULL DEFAULT 'free',  -- free, starter, professional, enterprise
    storage_limit_bytes BIGINT NOT NULL DEFAULT 5368709120,  -- 5GB
    instrument_limit INT NOT NULL DEFAULT 2,
    user_limit INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Organization membership
CREATE TABLE memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    role VARCHAR(20) NOT NULL DEFAULT 'scientist',  -- admin, scientist, viewer
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, organization_id)
);

-- Projects (sub-organization)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ
);

-- Instruments (registered in org)
CREATE TABLE instruments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    instrument_type VARCHAR(100) NOT NULL,  -- hplc, pcr, plate_reader, spectrophotometer, balance
    manufacturer VARCHAR(255),
    model VARCHAR(255),
    serial_number VARCHAR(255),
    location VARCHAR(255),
    agent_id UUID REFERENCES agents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Desktop agents
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    api_key_hash VARCHAR(255) NOT NULL,
    platform VARCHAR(20),  -- windows, macos, linux
    version VARCHAR(50),
    last_heartbeat_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, inactive, offline
    config JSONB DEFAULT '{}',  -- watched_folders, instrument_hints, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Uploads (raw instrument files)
CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    project_id UUID REFERENCES projects(id),
    instrument_id UUID REFERENCES instruments(id),
    agent_id UUID REFERENCES agents(id),
    uploaded_by UUID REFERENCES users(id),  -- NULL if uploaded by agent
    filename VARCHAR(500) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 for dedup
    file_size_bytes BIGINT NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'uploaded',  -- uploaded, parsing, parsed, parse_failed, indexed
    error_message TEXT,
    instrument_type_detected VARCHAR(100),
    parser_used VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsed_at TIMESTAMPTZ,
    indexed_at TIMESTAMPTZ,
    UNIQUE(organization_id, content_hash)  -- dedup within org
);

-- Parsed data (canonical model — ASM-compatible)
CREATE TABLE parsed_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id UUID NOT NULL REFERENCES uploads(id),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    instrument_type VARCHAR(100) NOT NULL,
    parser_version VARCHAR(50) NOT NULL,
    -- ASM-compatible fields
    measurement_type VARCHAR(100),  -- absorbance, fluorescence, concentration, mass, etc.
    sample_count INT,
    data_summary JSONB NOT NULL,  -- { "columns": [...], "row_count": N, "value_ranges": {...} }
    measurements JSONB NOT NULL,  -- Array of measurement objects
    units JSONB,  -- { "measurement_type": "absorbance", "unit": "AU", "qudt_uri": "..." }
    instrument_settings JSONB,  -- Method parameters, wavelengths, temperatures, etc.
    metadata JSONB DEFAULT '{}',  -- Additional context from the file
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiments
CREATE TABLE experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    project_id UUID REFERENCES projects(id),
    campaign_id UUID REFERENCES campaigns(id),
    intent TEXT NOT NULL,  -- What the experiment aims to achieve
    hypothesis TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'planned',  -- planned, running, completed, failed, cancelled
    parameters JSONB DEFAULT '{}',  -- Experimental conditions
    constraints JSONB DEFAULT '{}',  -- Bounds on parameters
    outcome JSONB,  -- Recorded after completion
    design_method VARCHAR(100),  -- manual, bayesian_optimization, etc.
    design_agent VARCHAR(100),  -- ID of agent that designed this experiment
    created_by UUID REFERENCES users(id),
    created_by_agent_token UUID REFERENCES api_tokens(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Experiment-upload links (many-to-many)
CREATE TABLE experiment_uploads (
    experiment_id UUID NOT NULL REFERENCES experiments(id),
    upload_id UUID NOT NULL REFERENCES uploads(id),
    linked_by UUID REFERENCES users(id),
    linked_by_agent_token UUID REFERENCES api_tokens(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (experiment_id, upload_id)
);

-- Experiment predecessor relationships
CREATE TABLE experiment_predecessors (
    experiment_id UUID NOT NULL REFERENCES experiments(id),
    predecessor_id UUID NOT NULL REFERENCES experiments(id),
    PRIMARY KEY (experiment_id, predecessor_id)
);

-- Campaigns (series of related experiments)
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    project_id UUID REFERENCES projects(id),
    name VARCHAR(255) NOT NULL,
    objective TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, paused, completed
    optimization_method VARCHAR(100),  -- bayesian, grid_search, manual, etc.
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- API tokens
CREATE TABLE api_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    created_by UUID NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    scope VARCHAR(20) NOT NULL DEFAULT 'read',  -- read, write, admin
    identity_type VARCHAR(20) NOT NULL DEFAULT 'user',  -- user, agent, integration
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit trail (immutable, append-only)
CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    actor_type VARCHAR(20) NOT NULL,  -- user, agent, system
    actor_id UUID,  -- user_id, agent_id, or NULL for system
    action VARCHAR(100) NOT NULL,  -- upload.created, experiment.status_changed, etc.
    resource_type VARCHAR(50) NOT NULL,  -- upload, experiment, project, etc.
    resource_id UUID NOT NULL,
    details JSONB DEFAULT '{}',  -- Before/after values, context
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hash VARCHAR(64) NOT NULL  -- SHA-256(previous_hash + this_event_data) for chain integrity
);

-- Webhooks
CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    url VARCHAR(2048) NOT NULL,
    secret VARCHAR(255) NOT NULL,  -- For HMAC-SHA256 signing
    events TEXT[] NOT NULL,  -- { 'upload.completed', 'parsing.completed', 'experiment.status_changed' }
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id UUID NOT NULL REFERENCES webhooks(id),
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, delivered, failed
    attempts INT NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    response_status INT,
    response_body TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_uploads_org_status ON uploads(organization_id, status);
CREATE INDEX idx_uploads_content_hash ON uploads(organization_id, content_hash);
CREATE INDEX idx_experiments_org_status ON experiments(organization_id, status);
CREATE INDEX idx_experiments_campaign ON experiments(campaign_id);
CREATE INDEX idx_audit_events_org_resource ON audit_events(organization_id, resource_type, resource_id);
CREATE INDEX idx_audit_events_created ON audit_events(organization_id, created_at);
CREATE INDEX idx_parsed_data_upload ON parsed_data(upload_id);
CREATE INDEX idx_agents_heartbeat ON agents(organization_id, last_heartbeat_at);
```

### Elasticsearch Index Mapping

```json
{
  "lablink_data": {
    "mappings": {
      "properties": {
        "upload_id": { "type": "keyword" },
        "organization_id": { "type": "keyword" },
        "project_id": { "type": "keyword" },
        "instrument_type": { "type": "keyword" },
        "instrument_name": { "type": "text" },
        "filename": { "type": "text" },
        "measurement_type": { "type": "keyword" },
        "sample_names": { "type": "text" },
        "tags": { "type": "keyword" },
        "operator": { "type": "keyword" },
        "experiment_id": { "type": "keyword" },
        "campaign_id": { "type": "keyword" },
        "data_summary": { "type": "text" },
        "created_at": { "type": "date" },
        "parsed_at": { "type": "date" }
      }
    }
  }
}
```

### Canonical Parsed Data Model (ASM-Compatible)

```python
# src/lablink/schemas/canonical.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class MeasurementValue(BaseModel):
    """Single measurement from an instrument."""
    sample_id: Optional[str] = None
    sample_name: Optional[str] = None
    well_position: Optional[str] = None  # For plate-based instruments (e.g., "A1")
    value: float
    unit: str  # SI or domain-standard unit
    qudt_uri: Optional[str] = None  # QUDT ontology reference
    measurement_type: str  # absorbance, fluorescence, concentration, mass, area, retention_time, ct_value
    channel: Optional[str] = None  # For multi-channel instruments
    wavelength_nm: Optional[float] = None
    timestamp: Optional[datetime] = None
    quality_flag: Optional[str] = None  # pass, fail, suspect, out_of_range

class InstrumentSettings(BaseModel):
    """Instrument method/settings used for the measurement."""
    method_name: Optional[str] = None
    temperature_c: Optional[float] = None
    wavelength_nm: Optional[float] = None
    excitation_nm: Optional[float] = None
    emission_nm: Optional[float] = None
    flow_rate_ml_min: Optional[float] = None
    injection_volume_ul: Optional[float] = None
    column_type: Optional[str] = None
    run_time_min: Optional[float] = None
    cycle_count: Optional[int] = None  # For PCR
    extra: dict = {}  # Instrument-specific settings

class ParsedResult(BaseModel):
    """Canonical output from any instrument parser."""
    parser_name: str
    parser_version: str
    instrument_type: str  # hplc, pcr, plate_reader, spectrophotometer, balance
    measurement_type: str  # The primary measurement type
    measurements: list[MeasurementValue]
    instrument_settings: Optional[InstrumentSettings] = None
    sample_count: int
    plate_layout: Optional[dict] = None  # For plate readers: { "rows": 8, "cols": 12, "format": "96-well" }
    run_metadata: dict = {}  # Operator, date, software version, etc.
    raw_headers: Optional[list[str]] = None  # Original column headers for reference
    warnings: list[str] = []  # Non-fatal parser warnings
```

---

## API Design

### Response Envelope

Every endpoint returns this structure:

```python
# src/lablink/schemas/envelope.py
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional
from datetime import datetime
import uuid

T = TypeVar("T")

class PaginationMeta(BaseModel):
    total_count: int
    page: int
    page_size: int
    has_more: bool

class ErrorDetail(BaseModel):
    code: str  # Machine-readable: "EXPERIMENT_NOT_FOUND"
    message: str  # Human-readable: "No experiment with ID 'exp-999'"
    field: Optional[str] = None  # Which field caused the error
    suggestion: Optional[str] = None  # Agent-actionable: "Use list_experiments to find valid IDs"
    retry: bool = False
    retry_after: Optional[int] = None  # Seconds

class ResponseMeta(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    pagination: Optional[PaginationMeta] = None

class Envelope(BaseModel, Generic[T]):
    data: Optional[T] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    errors: list[ErrorDetail] = []
```

### Endpoint Catalog

All endpoints are under `/api/v1/`. Every endpoint uses the `Envelope` response wrapper. Every endpoint has an `operation_id` matching the `verb_noun` pattern.

#### Auth Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| POST | /api/v1/auth/register | register_user | Register a new user account |
| POST | /api/v1/auth/login | login_user | Authenticate and receive JWT |
| POST | /api/v1/auth/refresh | refresh_token | Refresh an expired JWT |
| POST | /api/v1/auth/api-tokens | create_api_token | Create a scoped API token |
| GET | /api/v1/auth/api-tokens | list_api_tokens | List active API tokens |
| DELETE | /api/v1/auth/api-tokens/{id} | revoke_api_token | Revoke an API token |

#### Organization & Project Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| POST | /api/v1/organizations | create_organization | Create a new organization (lab) |
| GET | /api/v1/organizations/{id} | get_organization | Get organization details |
| PATCH | /api/v1/organizations/{id} | update_organization | Update organization settings |
| GET | /api/v1/organizations/{id}/members | list_members | List organization members |
| POST | /api/v1/organizations/{id}/members | invite_member | Invite a user to the organization |
| PATCH | /api/v1/organizations/{id}/members/{user_id} | update_member_role | Change a member's role |
| DELETE | /api/v1/organizations/{id}/members/{user_id} | remove_member | Remove a member |
| POST | /api/v1/projects | create_project | Create a new project |
| GET | /api/v1/projects | list_projects | List projects in the organization |
| GET | /api/v1/projects/{id} | get_project | Get project details |
| PATCH | /api/v1/projects/{id} | update_project | Update project settings |

#### Instrument & Agent Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| POST | /api/v1/instruments | register_instrument | Register a new instrument |
| GET | /api/v1/instruments | list_instruments | List instruments. Returns name, type, status, agent link. |
| GET | /api/v1/instruments/{id} | get_instrument | Get instrument details |
| PATCH | /api/v1/instruments/{id} | update_instrument | Update instrument metadata |
| POST | /api/v1/agents | register_agent | Register a new desktop agent, returns API key |
| GET | /api/v1/agents | list_agents | List registered agents with status |
| GET | /api/v1/agents/{id} | get_agent | Get agent details including last heartbeat |
| POST | /api/v1/agents/{id}/heartbeat | agent_heartbeat | Agent sends heartbeat with system info |

#### Upload & Parsing Endpoints (Ingestor Toolset)

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| POST | /api/v1/uploads | create_upload | Upload an instrument file. Multipart form-data. Returns upload_id. |
| GET | /api/v1/uploads | list_uploads | List uploads. Filter by status, instrument, date. |
| GET | /api/v1/uploads/{id} | get_upload | Get upload details including parsing status. |
| POST | /api/v1/uploads/{id}/reparse | reparse_upload | Trigger re-parsing of a failed or outdated upload. |
| GET | /api/v1/uploads/{id}/raw | download_raw_file | Download the original instrument file from S3. |
| GET | /api/v1/parsers | list_parsers | List available parsers with supported formats. |

#### Data & Search Endpoints (Explorer Toolset)

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| GET | /api/v1/data/{upload_id} | get_instrument_data | Get parsed data for an upload. Returns structured JSON with measurements, units, quality flags. |
| POST | /api/v1/search | search_catalog | Semantic search across all lab data. Returns ranked results. Use for natural-language queries. For exact ID lookups, use get_upload or get_experiment instead. |
| GET | /api/v1/data/{upload_id}/chart | get_chart_data | Get Plotly.js chart config + raw JSON data for an upload. Both human-viewable chart and machine-readable data. |
| POST | /api/v1/exports | create_export | Export data. Specify format (csv, xlsx, pdf, json), filters, and scope. Returns download URL. |

#### Experiment Endpoints (Planner Toolset)

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| POST | /api/v1/experiments | create_experiment | Register a new experiment with intent, parameters, and optional campaign link. Returns experiment_id. Write operation. |
| GET | /api/v1/experiments | list_experiments | List experiments matching filters. Returns summaries with ID, intent, status, date, instrument types. |
| GET | /api/v1/experiments/{id} | get_experiment | Get full experiment details including linked data, predecessors, and outcome. |
| PATCH | /api/v1/experiments/{id} | update_experiment | Update experiment status or metadata. |
| POST | /api/v1/experiments/{id}/outcome | record_outcome | Record the experiment outcome. Includes success/failure and measured results. |
| POST | /api/v1/experiments/{id}/link-upload | link_upload_to_experiment | Link an upload to an experiment. Many-to-many. |
| DELETE | /api/v1/experiments/{id}/link-upload/{upload_id} | unlink_upload_from_experiment | Remove a link between upload and experiment. |
| POST | /api/v1/campaigns | create_campaign | Create an optimization campaign (series of related experiments). |
| GET | /api/v1/campaigns | list_campaigns | List campaigns. |
| GET | /api/v1/campaigns/{id} | get_campaign | Get campaign details with linked experiments and progress summary. |
| GET | /api/v1/campaigns/{id}/progress | get_campaign_progress | Get optimization progress: experiment count, best result, trend. |

#### Webhook Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| POST | /api/v1/webhooks | create_webhook | Register a webhook for event notifications. |
| GET | /api/v1/webhooks | list_webhooks | List registered webhooks. |
| PATCH | /api/v1/webhooks/{id} | update_webhook | Update webhook URL or events. |
| DELETE | /api/v1/webhooks/{id} | delete_webhook | Delete a webhook. |
| GET | /api/v1/webhooks/{id}/deliveries | list_webhook_deliveries | List delivery attempts for a webhook. |

#### Audit Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| GET | /api/v1/audit | list_audit_events | List audit trail events. Filter by resource, actor, date. |
| GET | /api/v1/audit/{resource_type}/{resource_id} | get_resource_audit | Get audit trail for a specific resource. |

#### Admin Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| GET | /api/v1/admin/usage | get_usage_stats | Get storage, instrument, user counts vs. tier limits. |
| GET | /api/v1/admin/health | get_system_health | Health check for all services (DB, S3, ES, Redis). |

**Total: ~45 endpoints, organized into 8 domains.**

### MCP Server Toolsets

The MCP server exposes a curated subset. NOT a 1:1 mapping of all endpoints.

#### Discovery Tools (always loaded)

```
list_toolsets()         -> Available toolset categories with descriptions
get_toolset(name)       -> Tools in a specific toolset
```

#### Explorer Toolset (8 tools)

```
list_experiments(status?, campaign_id?, created_after?, instrument_type?, page?, page_size?)
get_experiment(experiment_id)
get_instrument_data(upload_id)
search_catalog(query, max_results?)
list_instruments()
list_uploads(status?, instrument_id?, created_after?, page?, page_size?)
get_chart_data(upload_id)
create_export(format, filters?)
```

#### Planner Toolset (7 tools)

```
create_experiment(intent, parameters?, campaign_id?, predecessor_ids?)
update_experiment(experiment_id, status?, outcome?)
record_outcome(experiment_id, results, success)
link_upload_to_experiment(experiment_id, upload_id)
create_campaign(name, objective, optimization_method?)
get_campaign_progress(campaign_id)
list_campaigns(status?)
```

#### Ingestor Toolset (4 tools)

```
create_upload(file, instrument_type?, project_id?)
list_parsers()
get_upload(upload_id)
reparse_upload(upload_id)
```

#### Admin Toolset (4 tools)

```
get_usage_stats()
list_agents()
create_webhook(url, events, secret?)
list_audit_events(resource_type?, resource_id?, created_after?, page?)
```

**Total: 25 MCP tools across 4 toolsets + 2 discovery tools. Within the 25-tool performance limit.**

### Webhook Events

| Event | Payload | Triggered When |
|-------|---------|---------------|
| `upload.created` | { upload_id, filename, instrument_type, file_size } | File uploaded successfully |
| `upload.parsed` | { upload_id, parser_used, sample_count, measurement_type } | Parsing completed successfully |
| `upload.parse_failed` | { upload_id, error_message, parser_attempted } | Parsing failed |
| `experiment.created` | { experiment_id, intent, campaign_id } | New experiment registered |
| `experiment.status_changed` | { experiment_id, old_status, new_status, changed_by } | Experiment status transition |
| `experiment.outcome_recorded` | { experiment_id, success, results_summary } | Outcome recorded |
| `agent.offline` | { agent_id, last_heartbeat, offline_duration } | Agent missed 3 consecutive heartbeats |

### Error Code Catalog

| Code | HTTP Status | Message Template | Suggestion |
|------|------------|-----------------|------------|
| `EXPERIMENT_NOT_FOUND` | 404 | No experiment with ID '{id}' | Use list_experiments to find valid experiment IDs |
| `UPLOAD_NOT_FOUND` | 404 | No upload with ID '{id}' | Use list_uploads to find valid upload IDs |
| `CAMPAIGN_NOT_FOUND` | 404 | No campaign with ID '{id}' | Use list_campaigns to find valid campaign IDs |
| `PARSE_FAILED` | 422 | Parser '{parser}' failed: {error} | Check file format. Use list_parsers to see supported formats. |
| `DUPLICATE_UPLOAD` | 409 | File with identical content hash already exists as upload '{id}' | Use get_upload with the existing upload ID |
| `INVALID_STATUS_TRANSITION` | 422 | Cannot transition from '{from}' to '{to}' | Valid transitions: planned->running, running->completed, running->failed, planned->cancelled |
| `RATE_LIMITED` | 429 | Rate limit exceeded ({limit}/min for {tier} tier) | Retry after {retry_after} seconds. Upgrade plan for higher limits. |
| `INSUFFICIENT_SCOPE` | 403 | Token scope '{scope}' cannot perform '{action}' | This action requires '{required_scope}' scope. Create a new token with appropriate scope. |
| `STORAGE_LIMIT_EXCEEDED` | 402 | Organization storage limit reached ({used}/{limit}) | Delete unused uploads or upgrade to a higher tier. |
| `INSTRUMENT_LIMIT_EXCEEDED` | 402 | Organization instrument limit reached ({count}/{limit}) | Remove unused instruments or upgrade tier. |
| `UNSUPPORTED_FORMAT` | 422 | No parser available for file type '{ext}' | Supported formats: {formats_list}. Use list_parsers for details. |
| `VALIDATION_ERROR` | 422 | Invalid value for '{field}': {detail} | Expected {expected_format}. Example: {example_value} |

---

## Project Structure

```
lablink/
├── CLAUDE.md                           # Agent coding instructions
├── CLAUDE.md                           # AI agent integration instructions
├── README.md
├── plans/
│   └── lablink-product-roadmap.md      # This file
├── RESEARCH/                           # Research documents (existing)
│
├── src/
│   ├── lablink/                        # Python backend (FastAPI)
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app factory, middleware, exception handlers
│   │   ├── config.py                   # Settings via pydantic-settings (env vars)
│   │   ├── database.py                 # SQLAlchemy async engine + session factory
│   │   ├── dependencies.py             # Shared FastAPI dependencies (get_db, get_current_user, get_org)
│   │   │
│   │   ├── schemas/                    # Pydantic schemas (request/response)
│   │   │   ├── __init__.py
│   │   │   ├── envelope.py             # Envelope[T], ErrorDetail, PaginationMeta
│   │   │   ├── canonical.py            # ParsedResult, MeasurementValue, InstrumentSettings
│   │   │   ├── auth.py                 # LoginRequest, TokenResponse, etc.
│   │   │   ├── organizations.py
│   │   │   ├── projects.py
│   │   │   ├── instruments.py
│   │   │   ├── agents.py
│   │   │   ├── uploads.py
│   │   │   ├── experiments.py
│   │   │   ├── campaigns.py
│   │   │   ├── webhooks.py
│   │   │   └── audit.py
│   │   │
│   │   ├── models/                     # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Base model with id, created_at, org_id
│   │   │   ├── organization.py
│   │   │   ├── user.py
│   │   │   ├── membership.py
│   │   │   ├── project.py
│   │   │   ├── instrument.py
│   │   │   ├── agent.py
│   │   │   ├── upload.py
│   │   │   ├── parsed_data.py
│   │   │   ├── experiment.py
│   │   │   ├── campaign.py
│   │   │   ├── api_token.py
│   │   │   ├── audit_event.py
│   │   │   ├── webhook.py
│   │   │   └── webhook_delivery.py
│   │   │
│   │   ├── routers/                    # FastAPI routers (thin — delegate to services)
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── organizations.py
│   │   │   ├── projects.py
│   │   │   ├── instruments.py
│   │   │   ├── agents.py
│   │   │   ├── uploads.py
│   │   │   ├── data.py                 # get_instrument_data, search_catalog, get_chart_data, exports
│   │   │   ├── experiments.py
│   │   │   ├── campaigns.py
│   │   │   ├── webhooks.py
│   │   │   ├── audit.py
│   │   │   └── admin.py
│   │   │
│   │   ├── services/                   # Business logic (zero HTTP awareness)
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── organization_service.py
│   │   │   ├── upload_service.py       # File reception, S3 upload, dedup check, kick off parse
│   │   │   ├── parser_service.py       # Parser selection, execution, canonical output
│   │   │   ├── search_service.py       # Elasticsearch queries
│   │   │   ├── experiment_service.py
│   │   │   ├── campaign_service.py
│   │   │   ├── webhook_service.py      # Fan-out, HMAC signing
│   │   │   ├── audit_service.py        # Append-only audit trail with hash chain
│   │   │   └── export_service.py
│   │   │
│   │   ├── parsers/                    # Instrument file parsers
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # BaseParser ABC — input: bytes + metadata, output: ParsedResult
│   │   │   ├── registry.py             # Parser registry: instrument_type -> parser class
│   │   │   ├── detector.py             # Auto-detect instrument type from file content
│   │   │   ├── spectrophotometer.py    # UV-Vis CSV parser
│   │   │   ├── plate_reader.py         # Template-based plate reader CSV parser
│   │   │   ├── hplc.py                # ANDI/CDF + vendor CSV parser
│   │   │   ├── pcr.py                 # RDML + vendor CSV parser (Bio-Rad, Thermo)
│   │   │   └── balance.py             # Simple weight reading CSV parser
│   │   │
│   │   ├── tasks/                      # Celery tasks
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py           # Celery configuration
│   │   │   ├── parse_task.py           # Parse uploaded file, store result, index in ES
│   │   │   ├── webhook_task.py         # Deliver webhook with retry + HMAC signing
│   │   │   ├── index_task.py           # Sync parsed data to Elasticsearch
│   │   │   └── reconciliation_task.py  # Periodic: check PG vs ES consistency
│   │   │
│   │   └── mcp/                        # MCP server
│   │       ├── __init__.py
│   │       └── server.py               # FastMCP server with curated toolsets
│   │
│   └── lablink_sdk/                    # Python SDK (pip install lablink)
│       ├── __init__.py
│       ├── client.py                   # LabLink class with typed methods
│       ├── models.py                   # SDK-side Pydantic models
│       └── exceptions.py              # Typed exceptions
│
├── agent/                              # Go desktop agent
│   ├── go.mod
│   ├── go.sum
│   ├── main.go                         # Entry point, CLI flags
│   ├── cmd/
│   │   └── root.go                     # Cobra CLI setup
│   ├── internal/
│   │   ├── config/
│   │   │   └── config.go               # YAML config loading (api_key, folders, hints)
│   │   ├── watcher/
│   │   │   └── watcher.go              # fsnotify file watcher with stability check
│   │   ├── queue/
│   │   │   └── queue.go                # BBolt persistent queue (store & forward)
│   │   ├── uploader/
│   │   │   └── uploader.go             # HTTPS upload with retry + exponential backoff
│   │   └── heartbeat/
│   │       └── heartbeat.go            # Periodic heartbeat to cloud
│   └── configs/
│       └── lablink-agent.example.yaml  # Example config file
│
├── frontend/                           # React dashboard
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/                        # API client (auto-generated from OpenAPI)
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   ├── dashboard/
│   │   │   ├── uploads/
│   │   │   ├── experiments/
│   │   │   ├── search/
│   │   │   └── charts/                 # Plotly.js wrapper components
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── UploadsPage.tsx
│   │   │   ├── ExperimentsPage.tsx
│   │   │   ├── SearchPage.tsx
│   │   │   ├── InstrumentsPage.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   └── AdminPage.tsx
│   │   └── hooks/
│   │       ├── useSSE.ts               # Server-Sent Events for real-time updates
│   │       └── useApi.ts
│   └── public/
│
├── migrations/                         # Alembic migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
│
├── tests/
│   ├── conftest.py                     # Fixtures: test DB, test client, test user, test org
│   ├── test_auth.py
│   ├── test_uploads.py
│   ├── test_parsers/
│   │   ├── test_spectrophotometer.py
│   │   ├── test_plate_reader.py
│   │   ├── test_hplc.py
│   │   ├── test_pcr.py
│   │   └── test_balance.py
│   ├── test_experiments.py
│   ├── test_search.py
│   ├── test_webhooks.py
│   ├── test_audit.py
│   ├── test_mcp_tools.py              # Agent accuracy tests
│   ├── test_tool_descriptions.py      # Tool description quality tests
│   └── fixtures/                       # Sample instrument files for parser tests
│       ├── spectrophotometer/
│       │   ├── nanodrop_sample.csv
│       │   └── cary_sample.csv
│       ├── plate_reader/
│       │   ├── molecular_devices_softmax.csv
│       │   └── biotek_gen5.csv
│       ├── hplc/
│       │   ├── agilent_chemstation.csv
│       │   └── shimadzu_labsolutions.csv
│       ├── pcr/
│       │   ├── biorad_cfx.csv
│       │   ├── thermo_quantstudio.eds.csv
│       │   └── sample.rdml
│       └── balance/
│           └── mettler_toledo.csv
│
├── docs/                               # Mintlify docs site
│   ├── docs.json                       # Mintlify config
│   ├── quickstart/
│   │   ├── for-developers.mdx
│   │   ├── for-CLAUDE.mdx
│   │   └── for-sdk-users.mdx
│   ├── api-reference/                  # Auto-generated from OpenAPI
│   └── mcp/
│       ├── overview.mdx
│       ├── toolsets.mdx
│       └── examples.mdx
│
├── infra/                              # Terraform infrastructure
│   ├── main.tf
│   ├── variables.tf
│   ├── ecs.tf                          # Fargate services for API + workers
│   ├── rds.tf                          # PostgreSQL
│   ├── s3.tf                           # Object storage
│   ├── elasticsearch.tf                # OpenSearch
│   ├── redis.tf                        # ElastiCache Redis
│   └── outputs.tf
│
├── docker-compose.yml                  # Local dev: PostgreSQL, Redis, Elasticsearch, MinIO (S3)
├── Dockerfile                          # Backend API
├── Dockerfile.worker                   # Celery worker
├── pyproject.toml                      # Python project config (backend + SDK)
├── Makefile                            # dev, test, lint, migrate, seed
└── .github/
    └── workflows/
        ├── ci.yml                      # Test + lint on PR
        └── deploy.yml                  # Deploy on merge to main
```

---

## 2-Year Roadmap

### Quarter 1: MVP (Months 1-2) — "Connect Your Lab"

**Objective:** Working product that ingests files from 5 instrument types, stores and indexes them, provides search and auto-visualization, with a fully agent-native API from day one.

**Success Criteria:**
- 10 design partner labs using the product
- 5 instrument parsers producing correct canonical output
- All API endpoints return structured JSON in the standard envelope
- MCP server functional with Claude Desktop
- End-to-end test: agent detects file -> uploads -> parses -> searchable in <30 seconds

#### Month 1: Foundation

**Week 1: Project Scaffolding + Core Backend**

Files to create:
- `pyproject.toml` — Python 3.12+, FastAPI 0.115+, SQLAlchemy 2.0+, Pydantic 2.12+, Celery 5.6+, all test deps
- `docker-compose.yml` — PostgreSQL 16, Redis 7, Elasticsearch 9, MinIO
- `Makefile` — targets: dev, test, lint, migrate, seed, format
- `src/lablink/main.py` — App factory with CORS, exception handlers, envelope middleware
- `src/lablink/config.py` — Settings from env vars (DATABASE_URL, REDIS_URL, S3_BUCKET, ES_URL, SECRET_KEY)
- `src/lablink/database.py` — Async SQLAlchemy engine, session factory, get_db dependency
- `src/lablink/dependencies.py` — get_current_user, get_current_org, require_role
- `src/lablink/schemas/envelope.py` — Envelope[T], ErrorDetail, PaginationMeta, ResponseMeta
- All SQLAlchemy models in `src/lablink/models/`
- `migrations/versions/001_initial_schema.py` — Full schema from above
- `src/lablink/routers/auth.py` — register, login, refresh, API token CRUD
- `src/lablink/services/auth_service.py` — JWT + bcrypt, API token generation with scope
- `src/lablink/routers/organizations.py` — CRUD + member management
- `src/lablink/routers/projects.py` — CRUD scoped to org
- `tests/conftest.py` — Test database, test client, authenticated user fixture, test org fixture
- `tests/test_auth.py` — Registration, login, token creation, scope enforcement
- `CLAUDE.md` — Project conventions for agentic coding tools
- `CLAUDE.md` — Instructions for AI agents working with the codebase
- `.gitignore`

**Week 2: Upload Pipeline + First Parser**

Files to create:
- `src/lablink/routers/uploads.py` — Upload endpoint (multipart/form-data), list, get, download
- `src/lablink/services/upload_service.py` — S3 upload, SHA-256 dedup check, kick off parse task
- `src/lablink/tasks/celery_app.py` — Celery config with Redis broker, separate queues for parsing/webhooks
- `src/lablink/tasks/parse_task.py` — Select parser, execute, store ParsedResult, update status
- `src/lablink/parsers/base.py` — BaseParser ABC: `parse(file_bytes: bytes, metadata: dict) -> ParsedResult`
- `src/lablink/parsers/registry.py` — Map instrument_type -> parser class, auto-detection logic
- `src/lablink/parsers/detector.py` — File type detection (extension + header analysis)
- `src/lablink/parsers/spectrophotometer.py` — NanoDrop/Cary UV-Vis CSV parser
- `src/lablink/schemas/canonical.py` — ParsedResult, MeasurementValue, InstrumentSettings
- `tests/fixtures/spectrophotometer/` — 2-3 real CSV samples from NanoDrop, Cary
- `tests/test_uploads.py` — Upload, dedup, status tracking
- `tests/test_parsers/test_spectrophotometer.py` — Parse known files, verify canonical output

**Week 3: Remaining Parsers + Search**

Files to create:
- `src/lablink/parsers/plate_reader.py` — Template-based CSV (SoftMax Pro, Gen5 layouts)
- `src/lablink/parsers/hplc.py` — ANDI/CDF + Agilent/Shimadzu CSV export
- `src/lablink/parsers/pcr.py` — RDML XML + Bio-Rad/Thermo CSV export
- `src/lablink/parsers/balance.py` — Mettler Toledo / Sartorius CSV parser
- `src/lablink/services/search_service.py` — Elasticsearch index management, query building
- `src/lablink/tasks/index_task.py` — Index parsed data to Elasticsearch
- `src/lablink/routers/data.py` — get_instrument_data, search_catalog, get_chart_data, create_export
- `tests/test_parsers/` — One test file per parser with 2-3 fixture files each
- `tests/test_search.py` — Index data, full-text search, filter by instrument/date/project

**Week 4: Experiments + Dashboard MVP**

Files to create:
- `src/lablink/routers/experiments.py` — Full experiment CRUD + linking + outcome
- `src/lablink/routers/campaigns.py` — Campaign CRUD + progress
- `src/lablink/services/experiment_service.py` — State machine enforcement, linking logic
- `src/lablink/services/audit_service.py` — Append-only audit trail with hash chain
- `src/lablink/routers/audit.py` — List audit events, per-resource audit
- `tests/test_experiments.py` — Create, transition, link, outcome, campaign progress
- `tests/test_audit.py` — Immutability verification, hash chain integrity
- `frontend/` — React scaffold with Vite, Tailwind, React Router
- `frontend/src/pages/DashboardPage.tsx` — Overview: recent uploads, experiments, agent status
- `frontend/src/pages/UploadsPage.tsx` — List uploads, status badges, click to view
- `frontend/src/pages/SearchPage.tsx` — Full-text search with filters
- `frontend/src/components/charts/PlotlyChart.tsx` — Generic Plotly wrapper for parsed data

#### Month 2: Agent Layer + Polish

**Week 5: MCP Server + Webhooks**

Files to create:
- `src/lablink/mcp/server.py` — FastMCP server with all 4 toolsets + 2 discovery tools
- `src/lablink/routers/webhooks.py` — CRUD for webhook subscriptions
- `src/lablink/services/webhook_service.py` — Fan-out, HMAC-SHA256 signing, delivery logging
- `src/lablink/tasks/webhook_task.py` — Deliver with retry + exponential backoff
- `tests/test_mcp_tools.py` — Agent selects correct tools for given queries
- `tests/test_tool_descriptions.py` — Quality checks: verb_noun names, return types in descriptions
- `tests/test_webhooks.py` — Registration, delivery, retry, HMAC verification

**Week 6: Go Agent**

Files to create:
- `agent/go.mod` — Go 1.22+, fsnotify v1.9, bbolt, cobra
- `agent/main.go` — CLI entry point
- `agent/cmd/root.go` — Cobra CLI: `lablink-agent start`, `lablink-agent configure`
- `agent/internal/config/config.go` — YAML config loading
- `agent/internal/watcher/watcher.go` — fsnotify watcher with 5-second stability check, extension filter
- `agent/internal/queue/queue.go` — BBolt persistent queue with retry counter + dead letter
- `agent/internal/uploader/uploader.go` — HTTPS multipart upload with exponential backoff (3 retries)
- `agent/internal/heartbeat/heartbeat.go` — 60-second heartbeat to /api/v1/agents/{id}/heartbeat
- `agent/configs/lablink-agent.example.yaml` — Example config
- Cross-compile for Windows amd64 + macOS arm64/amd64

**Week 7: Documentation + Infrastructure**

Files to create:
- `docs/docs.json` — Mintlify config pointing at OpenAPI spec
- `docs/quickstart/for-developers.mdx` — REST API quickstart
- `docs/quickstart/for-CLAUDE.mdx` — MCP server setup for Claude Desktop
- `docs/quickstart/for-sdk-users.mdx` — Python SDK quickstart
- `docs/mcp/overview.mdx` — MCP architecture explanation
- `docs/mcp/toolsets.mdx` — Toolset descriptions with examples
- `llms.txt` — Auto-generated tool index (~500 tokens)
- `llms-full.txt` — Full markdown API reference
- `infra/main.tf` — Terraform AWS setup
- `infra/ecs.tf` — Fargate for API (2 tasks) + Celery worker (1 task)
- `infra/rds.tf` — RDS PostgreSQL 16, db.t4g.medium
- `infra/s3.tf` — Bucket with lifecycle policies
- `infra/elasticsearch.tf` — OpenSearch t3.small.search
- `infra/redis.tf` — ElastiCache t4g.micro
- `Dockerfile` — Multi-stage build for API
- `Dockerfile.worker` — Celery worker image
- `.github/workflows/ci.yml` — pytest + ruff + mypy on PR
- `.github/workflows/deploy.yml` — Build + push to ECR + update ECS on merge to main

**Week 8: Integration Testing + Design Partner Onboarding**

- End-to-end test: Install agent -> watch folder -> drop file -> verify parsed + searchable
- Load test: 100 concurrent uploads, verify no data loss
- Security review: SQL injection, auth bypass, S3 access control
- First 5 design partner labs onboarded
- Feedback collection + bug fix sprint

### Quarter 2 (Months 3-4) — "Grow the Platform"

**Objective:** Expand instrument coverage, launch Python SDK, add collaboration features, begin compliance work. Public launch.

**Deliverables:**
- 5 more instrument parsers: flow cytometry (FCS), NMR (JCAMP-DX), UV-Vis (JCAMP-DX), mass spec (mzML basic), fluorescence plate reader
- `pip install lablink` Python SDK with type hints and async support
- Collaboration: invite by email, comments on uploads/experiments, activity feed
- SSE (Server-Sent Events) for real-time dashboard updates
- Public launch: Product Hunt + Show HN + open-source parser library
- Rate limiting per tier per token
- Manual upload via dashboard drag-and-drop (alongside agent)

**API additions:**
- `POST /api/v1/comments` — Add comment to any resource
- `GET /api/v1/activity` — Activity feed for a project
- `GET /api/v1/sse/updates` — SSE stream for real-time dashboard events
- `POST /api/v1/uploads/manual` — Browser-based file upload

**Success criteria:**
- 100 signups, 15 paying labs
- SDK published on PyPI
- Parser library open-sourced on GitHub with contribution guide
- MRR: $6K

### Quarter 3 (Months 5-6) — "Agent-Ready Platform"

**Objective:** Full MCP server polish, batch operations, event bus, plugin system. LabLink is now a first-class tool for AI agents.

**Deliverables:**
- MCP server published as standalone package (`pip install lablink-mcp`)
- Batch operations API: batch query, batch analysis, batch export
- Internal event bus (Redis Streams) for reactive workflows
- Plugin registry: third-party parsers can register and be discovered
- SOC 2 Type I certification (via Vanta/Drata)
- Electronic signatures for compliance workflows
- Agent audit trail (separate from human audit trail)
- Context7 integration for doc discovery by external agents

**API additions:**
- `POST /api/v1/batch/query` — Query multiple experiments in one call
- `POST /api/v1/batch/export` — Export multiple datasets
- `GET /api/v1/plugins` — List registered plugins
- `POST /api/v1/plugins` — Register a new plugin (parser or analysis)
- `GET /api/v1/events/subscribe` — SSE stream for programmatic event subscription

**New MCP tools:**
- `batch_query_experiments(experiment_ids)` — Get data for multiple experiments
- `batch_export(upload_ids, format)` — Export multiple datasets
- `list_plugins()` — Discover available third-party parsers/analysis tools

**Success criteria:**
- At least 2 external AI agent frameworks (MARS, ChemAgents, or custom LLMs) successfully using LabLink MCP tools
- Plugin registry has 3+ community-contributed parsers
- SOC 2 Type I achieved

### Quarter 4 (Months 7-8) — "Knowledge Layer"

**Objective:** Ontology-aware search, knowledge graph foundations, advanced analytics. LabLink becomes the knowledge backbone, not just a data store.

**Deliverables:**
- Ontology references in data model: ChEBI for chemicals, OBI for assays, QUDT for units
- Ontology-powered search: search by concept ("protease inhibitors") not just text
- Statistical analysis engine: curve fitting, outlier detection, standard deviation
- Advanced Plotly dashboards: overlay experiments, compare campaigns, trend lines
- AI anomaly detection: flag outliers in incoming data (basic ML model)
- Instrument drift tracking: detect calibration drift over time
- 21 CFR Part 11 compliance module
- SOC 2 Type II (requires 6+ months operating history)

**API additions:**
- `POST /api/v1/analysis/run` — Run statistical analysis on a dataset
- `GET /api/v1/analysis/methods` — List available analysis methods
- `GET /api/v1/anomalies` — Get detected anomalies across recent data
- `GET /api/v1/instruments/{id}/drift` — Get calibration drift history

**New MCP tools (Planner toolset update):**
- `run_analysis(dataset_id, method, config?)` — Trigger analysis
- `get_anomalies(instrument_id?, created_after?)` — Get flagged anomalies
- `get_instrument_drift(instrument_id)` — Calibration drift data

**Success criteria:**
- 60+ paying labs
- 21 CFR Part 11 module enables first pharma CRO customer
- MRR: $24K
- Agent-driven analysis workflow demonstrated end-to-end

### Quarter 5 (Months 9-10) — "Digital Twin Ready"

**Objective:** Capture the data that makes digital twins possible. Extended instrument metadata, environmental context, calibration tracking. Begin streaming API.

**Deliverables:**
- Extended instrument metadata schema: method parameters, calibration curves, maintenance history
- Environmental context capture: temperature, humidity, pressure (from IoT sensors via agent)
- Consumable tracking: column age/usage, reagent lots, solvent batches
- Streaming API (WebSocket) for real-time instrument data
- Serial port listener in Go agent (balances, pH meters, titrators — covers ~15% more instruments)
- SiLA 2 connector (basic) for automated instruments (Hamilton, Tecan, Beckman)
- Historical performance dashboards: instrument utilization, uptime, drift trends

**API additions:**
- `WS /api/v1/stream/{instrument_id}` — WebSocket for real-time instrument data
- `POST /api/v1/instruments/{id}/calibration` — Record calibration event
- `GET /api/v1/instruments/{id}/history` — Full instrument history
- `POST /api/v1/instruments/{id}/maintenance` — Record maintenance event

**Success criteria:**
- At least 1 lab using environmental context capture
- Serial port integration working for 3+ balance/pH meter models
- SiLA 2 connector tested with at least 1 Hamilton/Tecan instrument

### Quarter 6 (Months 11-12) — "Close the Loop"

**Objective:** Active learning feedback loop API. LabLink can now serve as the data backbone for a complete DMTA cycle. Partnership with 1-2 SDL frameworks.

**Deliverables:**
- Feedback loop API: analysis results can trigger experiment suggestions
- Integration with Bayesian optimization libraries (BoTorch, Gryffin)
- Experiment suggestion engine: given a campaign's history, suggest next parameters
- AlabOS integration: LabLink as the data layer for A-Lab style workflows
- UniLabOS compatibility: data export in UniLabOS-compatible format
- Knowledge graph (Neo4j): ontology-driven relationships between experiments, compounds, instruments
- Multi-site support: federate data across lab locations

**API additions:**
- `GET /api/v1/suggestions` — AI-generated experiment suggestions based on campaign data
- `POST /api/v1/campaigns/{id}/optimize` — Trigger optimization run
- `GET /api/v1/knowledge-graph/query` — SPARQL-like query over knowledge graph

**New MCP tools:**
- `get_suggestions(campaign_id)` — Get next experiment suggestions
- `query_knowledge_graph(query)` — Semantic query over lab knowledge

**Success criteria:**
- At least 1 closed-loop DMTA cycle demonstrated: AI designs experiment -> human/robot executes -> LabLink captures data -> AI analyzes -> AI suggests next experiment
- Partnership with AlabOS or UniLabOS team
- MRR: $50K+ (projection)

### Quarter 7 (Months 13-16) — "Scale the Platform"

**Deliverables:**
- HIPAA compliance (if clinical lab demand materializes)
- FedRAMP (if government lab demand)
- Advanced knowledge graph: experiment-compound-instrument-result relationships queryable by agents
- Microscopy support (Bio-Formats / OME-TIFF)
- Genomics data support (FASTQ, BAM — basic metadata, not full analysis)
- Marketplace for third-party integrations (ELN connectors, analysis tools)
- White-label option for instrument manufacturers
- Multi-region deployment (EU data residency)

### Quarter 8 (Months 17-24) — "The Autonomous Lab OS"

**Deliverables:**
- Full digital twin data model: enough metadata to simulate instrument runs in silico
- Protocol validation: LLM-generated lab protocols validated against instrument constraints
- Predictive maintenance: ML model predicts instrument failures from drift data
- Lab scheduling optimization: agent can schedule experiments across instruments
- Open SDL platform: LabLink as the canonical data layer for any self-driving lab
- Enterprise marketplace: curated integrations with Benchling, SciNote, LabWare, Empower
- Revenue target: $1M+ ARR, 200+ paying labs

---

## Technical Decisions & Defaults

These decisions resolve the critical ambiguities identified during specification analysis. They serve as defaults — override with explicit instructions if needed.

### Data Integrity

| Decision | Default | Rationale |
|----------|---------|-----------|
| **Source of truth** | PostgreSQL | Elasticsearch is eventually consistent, S3 is immutable blob store. PG is the authority. |
| **Dedup strategy** | SHA-256 content hash, unique per organization | Prevents duplicate uploads. Agent computes hash before upload, server verifies. |
| **Consistency model** | PG + S3 are synchronous (both must succeed). ES indexing is async via Celery task. | S3 failure blocks the upload (raw file must be preserved). ES can catch up. |
| **Reconciliation** | Periodic Celery beat task (every 5 min) checks PG records without ES index entries | Ensures search index stays in sync. |
| **Soft delete** | All deletes are soft (deleted_at timestamp). Hard delete after configurable retention (default 90 days). | Supports compliance and undo. Audit trail entries are never deleted. |
| **Hash chain** | Each audit event includes SHA-256(previous_hash + event_json). | Tamper evidence. Chain can be verified by sequential scan. |

### Agent Behavior

| Decision | Default | Rationale |
|----------|---------|-----------|
| **File stability check** | 5 seconds of no size change before queuing | Prevents partial file upload. Configurable per watched folder. |
| **Non-instrument files** | Filtered by extension whitelist (configurable, default: .csv, .tsv, .xml, .json, .txt, .rdml, .eds, .zpcr, .pcrd, .cdf, .fcs) | Ignores OS temp files, executables, etc. |
| **Queue size limit** | 10,000 files or 10GB, whichever first | Prevents disk exhaustion on instrument PC. Oldest entries are dead-lettered. |
| **Upload retry** | 3 attempts with exponential backoff (1s, 5s, 25s). After 3 failures, file moves to dead letter. | Handles transient network issues without infinite retry. |
| **Heartbeat interval** | 60 seconds | Cloud marks agent as "offline" after 3 missed heartbeats (3 min). |
| **Auto-update** | Check for updates on startup + every 24 hours. Download signed binary, verify signature, replace + restart. | Keeps agents current without IT involvement. |
| **Proxy support** | HTTP_PROXY / HTTPS_PROXY env vars respected. Also configurable in YAML config. | Supports corporate firewalls. |
| **Windows installation** | ZIP distribution (not MSI). Runs as user-level process. No admin required. Optional: register as Windows service via `sc create`. | Lowest friction for initial adoption. MSI in Phase 2. |

### API Behavior

| Decision | Default | Rationale |
|----------|---------|-----------|
| **Pagination** | Offset-based. Default page_size=20, max 100. | Simple for MVP. Cursor-based in Phase 2 if needed. |
| **Rate limiting** | Free: 60/min, Starter: 300/min, Pro: 1000/min, Enterprise: custom. Per-token. | HTTP 429 with Retry-After header. |
| **Search** | Full-text via Elasticsearch. Natural language queries parsed server-side. | Server-side reranking returns top results to minimize agent tokens. |
| **File size limit** | 500MB per upload for MVP. Larger files (microscopy, NGS) supported in Phase 2. | Covers all low/moderate tier instruments. |
| **Experiment-data linking** | Manual via API/UI. Auto-suggest based on time proximity + instrument type (UI only, not enforced). | Data exists independently of experiments. Experiments are optional context. |
| **Real-time updates** | Server-Sent Events (SSE) on `/api/v1/sse/updates`. Scoped to org. | Lighter than WebSocket, works through proxies. Dashboard polls as fallback. |
| **Instrument auto-detection** | 1) Agent provides instrument_type hint in metadata. 2) Server checks file extension. 3) Server analyzes file header (magic bytes, structure). 4) If uncertain, status = "unidentified", user prompted. | Multi-layer detection minimizes misclassification. |
| **Shared instruments** | Each agent belongs to one organization. Shared instruments at core facilities require a "core facility" org with cross-lab project access. | Simplest model for MVP. Multi-tenant agents in Phase 2. |

---

## Testing Strategy

### Unit Tests (per file)

Every service, parser, and schema has unit tests. Target: >90% coverage on services and parsers.

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from lablink.main import create_app
from lablink.database import get_db
from lablink.models.base import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()

@pytest.fixture
async def client(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def auth_headers(client):
    # Register + login, return {"Authorization": "Bearer <token>"}
    await client.post("/api/v1/auth/register", json={
        "email": "test@lab.com", "password": "TestPass123!", "full_name": "Test User"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "test@lab.com", "password": "TestPass123!"
    })
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

### Parser Tests

Each parser has tests with real instrument file fixtures:

```python
# tests/test_parsers/test_plate_reader.py
from lablink.parsers.plate_reader import PlateReaderParser
from lablink.schemas.canonical import ParsedResult

def test_softmax_pro_96well():
    with open("tests/fixtures/plate_reader/molecular_devices_softmax.csv", "rb") as f:
        result = PlateReaderParser().parse(f.read(), {"instrument_type": "plate_reader"})
    assert isinstance(result, ParsedResult)
    assert result.instrument_type == "plate_reader"
    assert result.sample_count == 96
    assert result.plate_layout["format"] == "96-well"
    assert all(m.unit == "AU" for m in result.measurements if m.measurement_type == "absorbance")
    assert len(result.warnings) == 0

def test_corrupted_file_returns_error():
    result = PlateReaderParser().parse(b"not a valid csv", {"instrument_type": "plate_reader"})
    # Parser should raise ParseError, not crash
```

### MCP Tool Tests

```python
# tests/test_tool_descriptions.py
from lablink.mcp.server import mcp

def test_all_tools_have_verb_noun_names():
    for tool in mcp.list_tools():
        parts = tool.name.split("_")
        assert len(parts) >= 2, f"Tool '{tool.name}' must be verb_noun"

def test_all_tools_describe_return_type():
    for tool in mcp.list_tools():
        desc = tool.description.lower()
        assert any(word in desc for word in ["returns", "return"]), \
            f"Tool '{tool.name}' description must mention what it returns"

def test_total_tool_count_under_limit():
    tools = mcp.list_tools()
    assert len(tools) <= 30, f"MCP server has {len(tools)} tools (max 30)"

def test_explorer_toolset_count():
    toolset = mcp.get_toolset("explorer")
    assert len(toolset) <= 10
```

### Integration Tests

```python
# tests/test_integration.py
async def test_full_upload_pipeline(client, auth_headers):
    """End-to-end: upload file -> parse -> search -> export."""
    # Upload a spectrophotometer file
    with open("tests/fixtures/spectrophotometer/nanodrop_sample.csv", "rb") as f:
        resp = await client.post(
            "/api/v1/uploads",
            files={"file": ("nanodrop.csv", f, "text/csv")},
            data={"instrument_type": "spectrophotometer"},
            headers=auth_headers
        )
    assert resp.status_code == 201
    upload_id = resp.json()["data"]["id"]

    # Wait for parsing (in test, run synchronously)
    resp = await client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers)
    assert resp.json()["data"]["status"] == "parsed"

    # Get parsed data
    resp = await client.get(f"/api/v1/data/{upload_id}", headers=auth_headers)
    data = resp.json()["data"]
    assert data["instrument_type"] == "spectrophotometer"
    assert len(data["measurements"]) > 0

    # Search
    resp = await client.post(
        "/api/v1/search",
        json={"query": "nanodrop absorbance"},
        headers=auth_headers
    )
    assert resp.json()["meta"]["pagination"]["total_count"] >= 1

    # Export
    resp = await client.post(
        "/api/v1/exports",
        json={"format": "csv", "upload_ids": [upload_id]},
        headers=auth_headers
    )
    assert resp.status_code == 200
```

---

## Key Configuration Files

### pyproject.toml

```toml
[project]
name = "lablink"
version = "0.1.0"
description = "Agent-native lab data integration platform"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.12.0",
    "pydantic-settings>=2.0.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.30.0",
    "alembic>=1.13.0",
    "celery[redis]>=5.6.0",
    "redis>=5.0.0",
    "elasticsearch[async]>=9.0.0",
    "boto3>=1.35.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-multipart>=0.0.9",
    "httpx>=0.27.0",
    "allotropy>=0.1.0",
    "fastmcp>=3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=1.0.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.5.0",
    "mypy>=1.11.0",
    "aiosqlite>=0.20.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
```

### docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: lablink
      POSTGRES_USER: lablink
      POSTGRES_PASSWORD: lablink_dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  elasticsearch:
    image: elasticsearch:9.0.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: lablink
      MINIO_ROOT_PASSWORD: lablink_dev
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data

volumes:
  pgdata:
  esdata:
  miniodata:
```

### Makefile

```makefile
.PHONY: dev test lint migrate seed format

dev:
	docker compose up -d
	uvicorn lablink.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --cov=src/lablink --cov-report=term-missing

lint:
	ruff check src/ tests/
	mypy src/lablink/

format:
	ruff format src/ tests/

migrate:
	alembic upgrade head

seed:
	python -m lablink.scripts.seed_dev_data
```

### CLAUDE.md

```markdown
# LabLink Development Conventions

## Stack
- Backend: Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Celery + Redis / PostgreSQL / Elasticsearch / S3
- Frontend: React + TypeScript + Tailwind + Plotly.js + Vite
- Desktop Agent: Go 1.22+ (fsnotify + BBolt)
- MCP Server: FastMCP 3.0+

## Architecture Principles
1. **Agent parity**: Every UI action has a corresponding API endpoint. No UI-only features.
2. **Structured outputs**: Every chart/visualization also returns machine-readable JSON.
3. **Composable tools**: API endpoints are atomic primitives (verb_noun). Agents compose them.
4. **Response envelope**: All endpoints return { data, meta, errors } via Envelope[T].
5. **Errors help agents recover**: Error responses include `suggestion` field with actionable fix.
6. **PostgreSQL is source of truth**: ES is eventually consistent. S3 is immutable.
7. **Immutable audit trail**: Append-only with hash chain. Never delete audit events.

## Code Organization
- Routers are thin: validate input, call service, return envelope.
- Services contain business logic: zero HTTP awareness, testable independently.
- Parsers follow BaseParser ABC: input (bytes + metadata), output ParsedResult.
- Models use SQLAlchemy 2.0 mapped_column style.
- Schemas use Pydantic v2 with Field descriptions (these become API docs + MCP tool descriptions).

## Naming Conventions
- API operation_ids: verb_noun snake_case (list_experiments, create_upload)
- Database tables: plural snake_case (experiments, parsed_data)
- Python files: singular snake_case (experiment.py, upload_service.py)
- Pydantic schemas: PascalCase (ExperimentCreate, UploadResponse)

## Testing
- pytest with asyncio_mode = "auto"
- Use httpx.AsyncClient with ASGITransport for API tests
- Override dependencies via app.dependency_overrides
- Parser tests use real fixture files in tests/fixtures/
- Every parser must have tests for: happy path, corrupted input, edge cases

## Running
- `make dev` — Start Docker services + API server
- `make test` — Run test suite
- `make lint` — Ruff + mypy
- `make migrate` — Run database migrations
```

---

## Evolution Path Summary

```
Q1 (M1-2)          Q2 (M3-4)          Q3 (M5-6)          Q4 (M7-8)
─────────────────────────────────────────────────────────────────────
DATA INTEGRATION    PLATFORM           AGENT-READY         KNOWLEDGE
─────────────────────────────────────────────────────────────────────
5 parsers           10 parsers         Plugin registry     Ontology search
Go agent            Python SDK         MCP package         Analysis engine
REST API            Collaboration      Batch API           Anomaly detection
Search              SSE real-time      Event bus           21 CFR Part 11
Experiments         Public launch      SOC 2 Type I        SOC 2 Type II
MCP server          Manual upload      Agent audit trail   Drift tracking
Webhooks            Rate limiting      Context7 docs       Knowledge graph

Q5 (M9-10)         Q6 (M11-12)        Q7 (M13-16)        Q8 (M17-24)
─────────────────────────────────────────────────────────────────────
DIGITAL TWIN        CLOSED LOOP        SCALE              AUTONOMOUS LAB OS
─────────────────────────────────────────────────────────────────────
Extended metadata   Feedback loop API  HIPAA              Digital twin sim
Environmental ctx   BoTorch/Gryffin    Microscopy         Protocol validation
Consumable track    Experiment suggest  Genomics basic     Predictive maint
Streaming API       AlabOS integration Marketplace        Lab scheduling
Serial port agent   UniLabOS compat    Multi-region       Open SDL platform
SiLA 2 basic        Knowledge graph    White-label        Enterprise market
Perf dashboards     Multi-site         FedRAMP            $1M+ ARR target
```
