# Agent-Native FastAPI Application: Implementation Best Practices (2025-2026)

Research compiled: March 2026
Target: LabLink Lab Data Integration Platform

---

## Table of Contents

1. [FastAPI Project Structure](#1-fastapi-project-structure)
2. [FastMCP Integration with FastAPI](#2-fastmcp-integration-with-fastapi)
3. [OpenAPI Spec Optimization for LLM Agents](#3-openapi-spec-optimization-for-llm-agents)
4. [Response Envelope Pattern](#4-response-envelope-pattern)
5. [Webhook/Event System with Celery + Redis](#5-webhookevent-system-with-celery--redis)
6. [Go Desktop Agent Patterns](#6-go-desktop-agent-patterns)
7. [Allotrope Simple Model (ASM)](#7-allotrope-simple-model-asm)
8. [Mintlify Docs with FastAPI](#8-mintlify-docs-with-fastapi)

---

## 1. FastAPI Project Structure

### Recommended Layout: Domain-Module Approach

For a 20-30 endpoint application like LabLink, the domain-module approach is strongly
preferred over file-type grouping. Each domain gets its own package containing all
related files.

```
lablink/
├── pyproject.toml
├── alembic/
│   ├── env.py
│   └── versions/
├── src/
│   └── lablink/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app factory, include_router calls
│       ├── config.py                  # Pydantic BaseSettings (split by domain)
│       ├── database.py                # async engine, sessionmaker, Base
│       ├── dependencies.py            # shared deps (get_db, get_current_user)
│       ├── middleware.py              # correlation IDs, timing, auth
│       ├── exceptions.py             # global exception classes + handlers
│       ├── envelope.py               # response envelope models (see section 4)
│       │
│       ├── instruments/              # === DOMAIN MODULE ===
│       │   ├── __init__.py
│       │   ├── router.py             # APIRouter, path operations only
│       │   ├── schemas.py            # Pydantic request/response models
│       │   ├── models.py             # SQLAlchemy ORM models
│       │   ├── service.py            # business logic (no HTTP concerns)
│       │   ├── dependencies.py       # domain-specific deps
│       │   ├── exceptions.py         # domain-specific exceptions
│       │   └── constants.py          # enums, magic values
│       │
│       ├── experiments/
│       │   ├── router.py
│       │   ├── schemas.py
│       │   ├── models.py
│       │   ├── service.py
│       │   └── ...
│       │
│       ├── uploads/                  # file upload + processing
│       │   ├── router.py
│       │   ├── schemas.py
│       │   ├── service.py
│       │   ├── tasks.py              # Celery tasks
│       │   └── parsers/              # ASM converters
│       │       ├── __init__.py
│       │       └── plate_reader.py
│       │
│       ├── webhooks/
│       │   ├── router.py             # webhook registration endpoints
│       │   ├── schemas.py
│       │   ├── service.py            # delivery logic
│       │   ├── models.py             # webhook subscriptions, delivery log
│       │   └── tasks.py              # Celery delivery tasks
│       │
│       ├── auth/
│       │   ├── router.py
│       │   ├── schemas.py
│       │   ├── service.py
│       │   └── jwt.py
│       │
│       └── mcp/
│           ├── __init__.py
│           └── server.py             # FastMCP.from_fastapi() setup
│
├── tests/
│   ├── conftest.py                   # fixtures: async client, test db
│   ├── instruments/
│   │   ├── test_router.py
│   │   └── test_service.py
│   └── ...
│
└── docs/                             # Mintlify docs repo (or separate repo)
    ├── docs.json                     # (formerly mint.json)
    ├── openapi.json                  # exported from FastAPI
    └── api-reference/
```

### Key Architectural Principles

**Service layer separation** (authority: zhanymkanov/fastapi-best-practices, widely adopted):

```python
# instruments/router.py -- thin, handles HTTP only
from fastapi import APIRouter, Depends, status
from .schemas import InstrumentCreate, InstrumentResponse
from .service import InstrumentService
from ..dependencies import get_db
from ..envelope import envelope

router = APIRouter(prefix="/instruments", tags=["instruments"])

@router.post(
    "",
    response_model=InstrumentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_instrument",
    summary="Register a new lab instrument",
    description="Registers an instrument (e.g., plate reader, HPLC) so its "
                "output files can be parsed into Allotrope Simple Model format.",
)
async def create_instrument(
    payload: InstrumentCreate,
    db=Depends(get_db),
):
    instrument = await InstrumentService(db).create(payload)
    return envelope(instrument)
```

```python
# instruments/service.py -- business logic, no HTTP imports
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Instrument
from .schemas import InstrumentCreate

class InstrumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: InstrumentCreate) -> Instrument:
        instrument = Instrument(**data.model_dump())
        self.db.add(instrument)
        await self.db.commit()
        await self.db.refresh(instrument)
        return instrument
```

**Dependency injection for validation** (FastAPI caches per-request):

```python
# instruments/dependencies.py
from fastapi import Depends, Path
from .service import InstrumentService
from ..dependencies import get_db
from .exceptions import InstrumentNotFound

async def valid_instrument(
    instrument_id: int = Path(..., description="Unique instrument ID"),
    db=Depends(get_db),
) -> Instrument:
    instrument = await InstrumentService(db).get(instrument_id)
    if not instrument:
        raise InstrumentNotFound(instrument_id)
    return instrument
```

**App factory in main.py:**

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .instruments.router import router as instruments_router
from .experiments.router import router as experiments_router
from .uploads.router import router as uploads_router
from .webhooks.router import router as webhooks_router
from .auth.router import router as auth_router
from .exceptions import register_exception_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: init DB pool, Redis connections
    yield
    # shutdown: cleanup

def create_app() -> FastAPI:
    app = FastAPI(
        title="LabLink API",
        version="1.0.0",
        description="Lab data integration platform -- ingest instrument files, "
                    "convert to Allotrope Simple Model, and push to LIMS/ELN.",
        lifespan=lifespan,
    )

    # Include routers with explicit prefixes for clarity
    app.include_router(auth_router,        prefix="/api/v1")
    app.include_router(instruments_router,  prefix="/api/v1")
    app.include_router(experiments_router,  prefix="/api/v1")
    app.include_router(uploads_router,      prefix="/api/v1")
    app.include_router(webhooks_router,     prefix="/api/v1")

    register_exception_handlers(app)
    return app

app = create_app()
```

### Library Versions (as of early 2026)

```toml
# pyproject.toml
[project]
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.10",
    "pydantic-settings>=2.6",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",          # async Postgres driver
    "alembic>=1.14",
    "httpx>=0.28",
    "celery[redis]>=5.4",
    "redis>=5.2",
    "fastmcp>=2.14",          # or >=3.0 if stable
    "allotropy>=0.1.65",      # Benchling ASM converters
    "orjson>=3.10",           # fast JSON serialization
    "python-multipart>=0.0.18",
]
```

---

## 2. FastMCP Integration with FastAPI

### Overview

FastMCP (https://gofastmcp.com) is the standard Python framework for building MCP
servers. Version 2.x introduced `FastMCP.from_fastapi()` which auto-generates an MCP
server from your existing FastAPI routes using the OpenAPI specification internally.

### Basic Integration

```python
# src/lablink/mcp/server.py
from fastmcp import FastMCP
from ..main import create_app

# Create the FastAPI app
fastapi_app = create_app()

# Auto-generate MCP server from all routes
mcp = FastMCP.from_fastapi(
    app=fastapi_app,
    name="LabLink MCP Server",
)

# You can still add hand-crafted tools for complex multi-step operations
@mcp.tool
async def parse_and_upload_instrument_file(
    file_path: str,
    instrument_type: str,
    experiment_id: int,
) -> dict:
    """Parse a raw instrument file into ASM format and attach to an experiment.

    This combines file upload, ASM conversion, and experiment linking into a
    single operation optimized for agent workflows.
    """
    # orchestration logic here
    ...
```

### RouteMap Customization

Control how endpoints map to MCP components (tools vs resources):

```python
from fastmcp.server.openapi import RouteMap, MCPType

mcp = FastMCP.from_fastapi(
    app=fastapi_app,
    name="LabLink MCP Server",
    route_maps=[
        # GET with path params -> resource templates (e.g., GET /instruments/{id})
        RouteMap(methods=["GET"], pattern=r".*\{.*\}.*",
                 mcp_type=MCPType.RESOURCE_TEMPLATE),
        # GET without path params -> resources (e.g., GET /instruments)
        RouteMap(methods=["GET"], pattern=r"^[^{]*$",
                 mcp_type=MCPType.RESOURCE),
        # POST/PUT/DELETE -> tools (default, but explicit)
        RouteMap(methods=["POST", "PUT", "DELETE"],
                 mcp_type=MCPType.TOOL),
    ],
)
```

### Combined Deployment (REST + MCP on same server)

```python
# main.py -- combined deployment
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans
from fastapi import FastAPI

def create_combined_app() -> FastAPI:
    # 1. Create base FastAPI app
    fastapi_app = create_app()

    # 2. Generate MCP server from it
    mcp = FastMCP.from_fastapi(app=fastapi_app, name="LabLink")
    mcp_asgi = mcp.http_app(path="/mcp")

    # 3. Mount MCP alongside REST
    combined = FastAPI(
        routes=[*mcp_asgi.routes, *fastapi_app.routes],
        lifespan=combine_lifespans(lifespan, mcp_asgi.lifespan),
    )
    return combined
```

This gives you:
- REST API at `https://lablink.example.com/api/v1/...`
- MCP endpoint at `https://lablink.example.com/mcp` (SSE or Streamable HTTP)

### Curating Tool Descriptions

The quality of auto-generated MCP tool descriptions depends entirely on your FastAPI
endpoint metadata. FastAPI operation IDs become MCP tool names.

**Critical**: Set `operation_id` explicitly on every route rather than relying on
auto-generated IDs (which produce names like `create_instrument_api_v1_instruments_post`).

```python
@router.post(
    "",
    operation_id="create_instrument",       # becomes the MCP tool name
    summary="Register a new lab instrument", # becomes the MCP tool description
    description="...",                       # extended description for agents
)
```

### When to Use Hand-Crafted Tools vs Auto-Generated

| Use Auto-Generated | Use Hand-Crafted `@mcp.tool` |
|---|---|
| Simple CRUD operations | Multi-step workflows |
| Single-resource lookups | Operations combining multiple endpoints |
| Straightforward create/update | Complex business logic with branching |
| Well-documented endpoints | Agent-optimized "macro" operations |

The FastMCP docs note that "LLMs achieve significantly better performance with
purpose-built MCP servers versus auto-converted OpenAPI implementations, particularly
for complex APIs." For LabLink, auto-generate the basic CRUD but hand-craft the
high-value agent workflows.

---

## 3. OpenAPI Spec Optimization for LLM Agents

### Why This Matters

When an LLM agent receives your API's tool list, it relies on operation IDs,
descriptions, and parameter schemas to decide which tool to call and how. Poor
naming leads to wrong tool selection; poor descriptions lead to wrong parameters.

### Operation ID Naming Convention

**Authority**: AWS Amazon Q Business best practices, Google ADK docs, widely adopted.

Rules:
1. Use verb_noun format: `create_instrument`, `list_experiments`, `upload_file`
2. Verb must reflect the action: `get`, `list`, `create`, `update`, `delete`, `search`, `parse`, `upload`
3. Noun must be the business domain object, not the URL path
4. No redundant prefixes: not `lablink_api_v1_create_instrument`, just `create_instrument`
5. Consistent across the API: if you use `experiment_id` in one place, use it everywhere

```python
# GOOD operation IDs for LabLink
"create_instrument"
"get_instrument"
"list_instruments"
"upload_instrument_file"
"parse_file_to_asm"
"create_experiment"
"get_experiment_results"
"register_webhook"
"list_webhook_deliveries"

# BAD operation IDs
"post_instruments"          # verb doesn't describe business action
"instrumentEndpoint"        # ambiguous
"api_v1_instruments_post"   # auto-generated noise
"doUpload"                  # vague noun
```

### Description Writing for Agent Consumption

```python
@router.post(
    "/files",
    operation_id="upload_instrument_file",
    summary="Upload a raw instrument output file for parsing",
    description=(
        "Accepts a raw output file from a supported lab instrument "
        "(plate reader, HPLC, qPCR, etc.) and queues it for conversion "
        "to Allotrope Simple Model (ASM) format. Returns a file_id that "
        "can be used with get_file_status to check processing progress. "
        "Supported formats: CSV, TSV, XLSX, TXT. Maximum file size: 50MB."
    ),
)
```

Key description principles:
- **Self-contained**: never reference external docs URLs
- **Explain when to use it**: "Use this when you need to..."
- **State what it returns**: "Returns a file_id that can be used with..."
- **List constraints**: file types, size limits, required permissions
- **Reference related operations by operation_id**: "Use `get_file_status` to check..."

### Parameter Documentation

```python
from pydantic import Field

class InstrumentFileUpload(BaseModel):
    instrument_id: int = Field(
        ...,
        description="ID of the registered instrument that produced this file. "
                    "Use list_instruments to find available instruments.",
    )
    file_format: str = Field(
        ...,
        description="File format of the uploaded data",
        json_schema_extra={"enum": ["csv", "tsv", "xlsx", "txt"]},
    )
    experiment_id: int | None = Field(
        None,
        description="Optional experiment to link this file to. "
                    "If not provided, the file is uploaded as unlinked.",
    )
```

Rules for parameters:
- Keep total parameters under 10, ideally under 5
- Use descriptive names: `instrument_id` not `id`, `start_date` not `start`
- Use `enum` for constrained values
- Use `format: date` / `format: date-time` instead of describing formats in text
- Flatten nested objects: `start_date` + `end_date` not `date_range: {start, end}`
- Consistent naming: same concept = same parameter name across all endpoints

### Custom generate_unique_id_function

For full control over auto-generated operation IDs across all routes:

```python
from fastapi.routing import APIRoute

def generate_operation_id(route: APIRoute) -> str:
    """Generate clean operation IDs from route tags and function names."""
    # Uses the function name directly, which should be descriptive
    return route.endpoint.__name__

app = FastAPI(
    generate_unique_id_function=generate_operation_id,
)
```

---

## 4. Response Envelope Pattern

### The Pattern

Every API response wrapped in a consistent structure:

```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-03-05T10:30:00Z",
    "pagination": { "page": 1, "per_page": 20, "total": 142 }
  },
  "errors": null
}
```

On error:
```json
{
  "data": null,
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-03-05T10:30:00Z"
  },
  "errors": [
    {
      "code": "INSTRUMENT_NOT_FOUND",
      "message": "Instrument with ID 42 not found",
      "field": null
    }
  ]
}
```

### Pydantic Implementation

```python
# src/lablink/envelope.py
from datetime import datetime, timezone
from typing import Generic, TypeVar
from pydantic import BaseModel, Field
import uuid

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class ResponseMeta(BaseModel):
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pagination: PaginationMeta | None = None


class ErrorDetail(BaseModel):
    code: str = Field(
        ..., description="Machine-readable error code, e.g., INSTRUMENT_NOT_FOUND"
    )
    message: str = Field(
        ..., description="Human-readable error description"
    )
    field: str | None = Field(
        None, description="Which request field caused the error, if applicable"
    )


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    errors: list[ErrorDetail] | None = None


# Convenience constructors
def envelope(data: T, **meta_kwargs) -> dict:
    """Wrap successful response data in the standard envelope."""
    meta = ResponseMeta(**meta_kwargs)
    return Envelope(data=data, meta=meta).model_dump(mode="json")


def paginated_envelope(
    data: list[T],
    page: int,
    per_page: int,
    total: int,
) -> dict:
    """Wrap paginated list response."""
    pagination = PaginationMeta(
        page=page,
        per_page=per_page,
        total=total,
        total_pages=(total + per_page - 1) // per_page,
    )
    meta = ResponseMeta(pagination=pagination)
    return Envelope(data=data, meta=meta).model_dump(mode="json")


def error_envelope(errors: list[ErrorDetail], status_code: int = 400) -> dict:
    """Wrap error response."""
    return Envelope(errors=errors).model_dump(mode="json")
```

### Exception Handler Integration

```python
# src/lablink/exceptions.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .envelope import ErrorDetail, error_envelope


class AppException(Exception):
    """Base application exception."""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


class InstrumentNotFound(AppException):
    def __init__(self, instrument_id: int):
        super().__init__(
            code="INSTRUMENT_NOT_FOUND",
            message=f"Instrument with ID {instrument_id} not found",
            status_code=404,
        )


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope([
                ErrorDetail(code=exc.code, message=exc.message)
            ]),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = [
            ErrorDetail(
                code="VALIDATION_ERROR",
                message=err["msg"],
                field=".".join(str(loc) for loc in err["loc"]),
            )
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_envelope(errors),
        )
```

### Using with response_model

```python
from .envelope import Envelope
from .instruments.schemas import InstrumentResponse

@router.get(
    "/{instrument_id}",
    response_model=Envelope[InstrumentResponse],
    operation_id="get_instrument",
)
async def get_instrument(instrument=Depends(valid_instrument)):
    return envelope(InstrumentResponse.model_validate(instrument))
```

---

## 5. Webhook/Event System with Celery + Redis

### Architecture

```
Event Occurs -> Redis Pub/Sub or DB trigger
    -> Celery task: deliver_webhook
        -> HTTP POST to subscriber URL
            -> success: log delivery
            -> failure: retry with exponential backoff (max 5 attempts)
                -> still failing: mark as failed, alert
```

### Data Models

```python
# src/lablink/webhooks/models.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum as SAEnum
from ..database import Base
import enum

class WebhookEvent(str, enum.Enum):
    FILE_UPLOADED = "file.uploaded"
    FILE_PARSED = "file.parsed"
    FILE_PARSE_FAILED = "file.parse_failed"
    EXPERIMENT_CREATED = "experiment.created"
    EXPERIMENT_UPDATED = "experiment.updated"
    RESULTS_READY = "results.ready"

class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)
    events = Column(JSON, nullable=False)         # list of WebhookEvent values
    secret = Column(String, nullable=False)        # HMAC signing secret
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey("webhook_subscriptions.id"))
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    response_status = Column(Integer, nullable=True)
    response_body = Column(String, nullable=True)
    attempt_count = Column(Integer, default=0)
    status = Column(String, default="pending")     # pending, delivered, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
```

### Celery Task with Retry

```python
# src/lablink/webhooks/tasks.py
import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx
from celery import shared_task

@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,      # first retry after 60s
    retry_backoff=True,          # exponential: 60, 120, 240, 480, 960
    retry_backoff_max=3600,      # cap at 1 hour
    retry_jitter=True,           # add randomness to prevent thundering herd
)
def deliver_webhook(self, delivery_id: int):
    """Deliver a webhook payload to the subscriber URL."""
    from .models import WebhookDelivery, WebhookSubscription
    from ..database import get_sync_session

    with get_sync_session() as db:
        delivery = db.get(WebhookDelivery, delivery_id)
        subscription = db.get(WebhookSubscription, delivery.subscription_id)

        # Sign payload with HMAC-SHA256
        payload_bytes = json.dumps(delivery.payload).encode()
        signature = hmac.new(
            subscription.secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-LabLink-Signature": f"sha256={signature}",
            "X-LabLink-Event": delivery.event_type,
            "X-LabLink-Delivery": str(delivery.id),
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    subscription.url,
                    content=payload_bytes,
                    headers=headers,
                )
                response.raise_for_status()

            delivery.status = "delivered"
            delivery.response_status = response.status_code
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.attempt_count += 1
            db.commit()

        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
            delivery.attempt_count += 1
            delivery.response_status = getattr(exc, "response", None) and exc.response.status_code
            db.commit()

            if self.request.retries >= self.max_retries:
                delivery.status = "failed"
                db.commit()
                # TODO: send alert to admin
                return

            raise self.retry(exc=exc)
```

### Event Emission Helper

```python
# src/lablink/webhooks/service.py
from .models import WebhookSubscription, WebhookDelivery, WebhookEvent
from .tasks import deliver_webhook

class WebhookService:
    def __init__(self, db):
        self.db = db

    async def emit(self, event: WebhookEvent, payload: dict):
        """Fan out a webhook event to all active subscribers."""
        subscriptions = await self.db.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.is_active == True,
                WebhookSubscription.events.contains([event.value]),
            )
        )
        for sub in subscriptions.scalars():
            delivery = WebhookDelivery(
                subscription_id=sub.id,
                event_type=event.value,
                payload=payload,
            )
            self.db.add(delivery)
            await self.db.flush()

            # Queue async delivery
            deliver_webhook.delay(delivery.id)

        await self.db.commit()
```

### Usage in Business Logic

```python
# In uploads/service.py after successful parse:
await webhook_service.emit(
    WebhookEvent.FILE_PARSED,
    {
        "file_id": file.id,
        "instrument_id": file.instrument_id,
        "experiment_id": file.experiment_id,
        "asm_schema": "plate-reader/BENCHLING/2024/09",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    },
)
```

### Celery Configuration

```python
# src/lablink/celery_app.py
from celery import Celery

celery_app = Celery(
    "lablink",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_routes={
        "lablink.webhooks.tasks.*": {"queue": "webhooks"},
        "lablink.uploads.tasks.*": {"queue": "uploads"},
    },
    task_default_queue="default",
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,      # fair scheduling for webhook delivery
    task_acks_late=True,               # ack after completion, not before
    redis_backend_health_check_interval=30,
)
```

---

## 6. Go Desktop Agent Patterns

### Architecture Overview

The Go desktop agent watches designated folders for new instrument output files,
queues them for upload, and uses a store-and-forward pattern to handle offline
scenarios.

```
┌────────────────────────────────────────────┐
│           Go Desktop Agent                  │
│                                            │
│  ┌──────────┐   ┌──────────┐   ┌────────┐ │
│  │ fsnotify │──>│  Queue   │──>│ Upload │ │
│  │ watcher  │   │ (bbolt)  │   │ worker │ │
│  └──────────┘   └──────────┘   └────────┘ │
│       │              │              │       │
│  watches dirs   persists to     HTTPS POST │
│  for new files  embedded DB     to LabLink │
│                                    API     │
└────────────────────────────────────────────┘
```

### Project Structure

```
lablink-agent/
├── cmd/
│   └── lablink-agent/
│       └── main.go              # entry point, CLI flags
├── internal/
│   ├── config/
│   │   └── config.go            # YAML config loading
│   ├── watcher/
│   │   └── watcher.go           # fsnotify wrapper
│   ├── queue/
│   │   └── queue.go             # bbolt-backed persistent queue
│   ├── uploader/
│   │   └── uploader.go          # HTTPS upload with retry
│   └── agent/
│       └── agent.go             # orchestrator
├── configs/
│   └── lablink-agent.yaml       # default config
├── go.mod
└── go.sum
```

### Key Dependencies

```go
// go.mod
module github.com/lablink/lablink-agent

go 1.23

require (
    github.com/fsnotify/fsnotify v1.8.0
    go.etcd.io/bbolt v1.4.0
    gopkg.in/yaml.v3 v3.0.1
)
```

### File Watcher with fsnotify

```go
// internal/watcher/watcher.go
package watcher

import (
    "log/slog"
    "path/filepath"
    "strings"

    "github.com/fsnotify/fsnotify"
)

type FileHandler func(path string)

type Watcher struct {
    fsw        *fsnotify.Watcher
    extensions []string // e.g., [".csv", ".xlsx", ".txt"]
    handler    FileHandler
    logger     *slog.Logger
}

func New(extensions []string, handler FileHandler, logger *slog.Logger) (*Watcher, error) {
    fsw, err := fsnotify.NewWatcher()
    if err != nil {
        return nil, err
    }
    return &Watcher{
        fsw:        fsw,
        extensions: extensions,
        handler:    handler,
        logger:     logger,
    }, nil
}

func (w *Watcher) Watch(dirs []string) error {
    for _, dir := range dirs {
        if err := w.fsw.Add(dir); err != nil {
            return err
        }
        w.logger.Info("watching directory", "path", dir)
    }

    go w.loop()
    return nil
}

func (w *Watcher) loop() {
    // debounce map to handle multiple write events for same file
    for {
        select {
        case event, ok := <-w.fsw.Events:
            if !ok {
                return
            }
            if !event.Has(fsnotify.Create) && !event.Has(fsnotify.Write) {
                continue
            }
            ext := strings.ToLower(filepath.Ext(event.Name))
            for _, allowed := range w.extensions {
                if ext == allowed {
                    w.logger.Info("file detected", "path", event.Name, "op", event.Op)
                    w.handler(event.Name)
                    break
                }
            }

        case err, ok := <-w.fsw.Errors:
            if !ok {
                return
            }
            w.logger.Error("watcher error", "err", err)
        }
    }
}

func (w *Watcher) Close() error {
    return w.fsw.Close()
}
```

### BBolt Persistent Queue (Store-and-Forward)

```go
// internal/queue/queue.go
package queue

import (
    "encoding/json"
    "fmt"
    "time"

    bolt "go.etcd.io/bbolt"
)

var bucketName = []byte("upload_queue")

type Item struct {
    ID        uint64    `json:"id"`
    FilePath  string    `json:"file_path"`
    AddedAt   time.Time `json:"added_at"`
    Retries   int       `json:"retries"`
    LastError string    `json:"last_error,omitempty"`
}

type Queue struct {
    db *bolt.DB
}

func Open(path string) (*Queue, error) {
    db, err := bolt.Open(path, 0600, &bolt.Options{Timeout: 1 * time.Second})
    if err != nil {
        return nil, err
    }
    // Ensure bucket exists
    err = db.Update(func(tx *bolt.Tx) error {
        _, err := tx.CreateBucketIfNotExists(bucketName)
        return err
    })
    return &Queue{db: db}, err
}

func (q *Queue) Enqueue(filePath string) error {
    return q.db.Update(func(tx *bolt.Tx) error {
        b := tx.Bucket(bucketName)
        id, _ := b.NextSequence()
        item := Item{
            ID:       id,
            FilePath: filePath,
            AddedAt:  time.Now().UTC(),
        }
        data, err := json.Marshal(item)
        if err != nil {
            return err
        }
        return b.Put(itob(id), data)
    })
}

func (q *Queue) Peek(limit int) ([]Item, error) {
    var items []Item
    err := q.db.View(func(tx *bolt.Tx) error {
        b := tx.Bucket(bucketName)
        c := b.Cursor()
        count := 0
        for k, v := c.First(); k != nil && count < limit; k, v = c.Next() {
            var item Item
            if err := json.Unmarshal(v, &item); err != nil {
                continue
            }
            items = append(items, item)
            count++
        }
        return nil
    })
    return items, err
}

func (q *Queue) Remove(id uint64) error {
    return q.db.Update(func(tx *bolt.Tx) error {
        return tx.Bucket(bucketName).Delete(itob(id))
    })
}

func (q *Queue) UpdateRetry(id uint64, lastErr string) error {
    return q.db.Update(func(tx *bolt.Tx) error {
        b := tx.Bucket(bucketName)
        data := b.Get(itob(id))
        if data == nil {
            return fmt.Errorf("item %d not found", id)
        }
        var item Item
        json.Unmarshal(data, &item)
        item.Retries++
        item.LastError = lastErr
        updated, _ := json.Marshal(item)
        return b.Put(itob(id), updated)
    })
}

func (q *Queue) Close() error { return q.db.Close() }

func itob(v uint64) []byte {
    b := make([]byte, 8)
    b[0] = byte(v >> 56)
    b[1] = byte(v >> 48)
    b[2] = byte(v >> 40)
    b[3] = byte(v >> 32)
    b[4] = byte(v >> 24)
    b[5] = byte(v >> 16)
    b[6] = byte(v >> 8)
    b[7] = byte(v)
    return b
}
```

### Upload Worker with Retry

```go
// internal/uploader/uploader.go
package uploader

import (
    "bytes"
    "context"
    "fmt"
    "io"
    "log/slog"
    "mime/multipart"
    "net/http"
    "os"
    "path/filepath"
    "time"

    "github.com/lablink/lablink-agent/internal/queue"
)

type Uploader struct {
    client    *http.Client
    apiURL    string
    apiKey    string
    queue     *queue.Queue
    logger    *slog.Logger
    maxRetry  int
    batchSize int
    interval  time.Duration
}

func New(apiURL, apiKey string, q *queue.Queue, logger *slog.Logger) *Uploader {
    return &Uploader{
        client: &http.Client{Timeout: 120 * time.Second},
        apiURL: apiURL,
        apiKey: apiKey,
        queue:  q,
        logger: logger,
        maxRetry:  10,
        batchSize: 5,
        interval:  10 * time.Second,
    }
}

func (u *Uploader) Run(ctx context.Context) {
    ticker := time.NewTicker(u.interval)
    defer ticker.Stop()

    for {
        select {
        case <-ctx.Done():
            return
        case <-ticker.C:
            u.processBatch(ctx)
        }
    }
}

func (u *Uploader) processBatch(ctx context.Context) {
    items, err := u.queue.Peek(u.batchSize)
    if err != nil {
        u.logger.Error("failed to peek queue", "err", err)
        return
    }

    for _, item := range items {
        if item.Retries >= u.maxRetry {
            u.logger.Error("max retries exceeded, moving to dead letter",
                "path", item.FilePath, "retries", item.Retries)
            u.queue.Remove(item.ID) // or move to dead-letter bucket
            continue
        }

        err := u.uploadFile(ctx, item.FilePath)
        if err != nil {
            u.logger.Warn("upload failed, will retry",
                "path", item.FilePath, "err", err, "retry", item.Retries+1)
            u.queue.UpdateRetry(item.ID, err.Error())
            continue
        }

        u.logger.Info("upload succeeded", "path", item.FilePath)
        u.queue.Remove(item.ID)
    }
}

func (u *Uploader) uploadFile(ctx context.Context, filePath string) error {
    file, err := os.Open(filePath)
    if err != nil {
        return fmt.Errorf("open file: %w", err)
    }
    defer file.Close()

    var buf bytes.Buffer
    writer := multipart.NewWriter(&buf)
    part, err := writer.CreateFormFile("file", filepath.Base(filePath))
    if err != nil {
        return err
    }
    if _, err := io.Copy(part, file); err != nil {
        return err
    }
    writer.Close()

    req, err := http.NewRequestWithContext(ctx, "POST",
        u.apiURL+"/api/v1/uploads/files", &buf)
    if err != nil {
        return err
    }
    req.Header.Set("Content-Type", writer.FormDataContentType())
    req.Header.Set("Authorization", "Bearer "+u.apiKey)

    resp, err := u.client.Do(req)
    if err != nil {
        return fmt.Errorf("http request: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode >= 400 {
        body, _ := io.ReadAll(resp.Body)
        return fmt.Errorf("server returned %d: %s", resp.StatusCode, string(body))
    }
    return nil
}
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Queue persistence | BBolt (embedded) | No external deps, single-file DB, crash-safe via B+ tree |
| Watch approach | fsnotify (OS events) | Low CPU, instant detection; fall back to polling for NFS |
| Retry strategy | Exponential backoff | Prevent hammering server during outages |
| Upload transport | multipart/form-data | Standard file upload, proxy-friendly |
| Config | YAML file | Lab IT can edit without recompiling |
| Dead-letter handling | Separate bbolt bucket | Failed items preserved for manual review |
| Binary distribution | goreleaser | Cross-platform builds for Windows/macOS/Linux |

---

## 7. Allotrope Simple Model (ASM)

### Benchling's allotropy Library

**Repository**: https://github.com/Benchling-Open-Source/allotropy
**License**: MIT
**Python**: 3.10+
**Install**: `pip install allotropy`

This is THE open-source reference implementation for ASM conversion. It converts
text/Excel instrument output files to JSON conforming to the Allotrope Simple Model
schema.

### Basic Usage

```python
from allotropy.parser_factory import Vendor
from allotropy.to_allotrope import allotrope_from_file, allotrope_from_io

# From a file path
asm_dict = allotrope_from_file(
    "path/to/plate_reader_output.csv",
    Vendor.MOLDEV_SOFTMAX_PRO,
)

# From an IO object (e.g., uploaded file)
asm_dict = allotrope_from_io(
    uploaded_file.file,   # any file-like object
    Vendor.MOLDEV_SOFTMAX_PRO,
)
```

### Supported Instrument Vendors (partial list)

The library maintains an extensive list in SUPPORTED_INSTRUMENT_SOFTWARE.adoc.
Key vendors include:
- Molecular Devices (SoftMax Pro)
- PerkinElmer (EnVision)
- BMG Labtech (various readers)
- Agilent (various HPLC, plate readers)
- Bio-Rad
- Thermo Fisher
- Roche (LightCycler)
- Applied Biosystems (QuantStudio)
- Beckman Coulter
- Luminex
- Meso Scale Discovery

### Integration with LabLink

```python
# src/lablink/uploads/parsers/asm_converter.py
from allotropy.parser_factory import Vendor
from allotropy.to_allotrope import allotrope_from_io
from allotropy.exceptions import AllotropeConversionError

# Map LabLink instrument types to allotropy vendors
VENDOR_MAP: dict[str, Vendor] = {
    "softmax_pro": Vendor.MOLDEV_SOFTMAX_PRO,
    "envision": Vendor.PERKIN_ELMER_ENVISION,
    "quantstudio": Vendor.APPBIO_QUANTSTUDIO,
    "clariostar": Vendor.BMG_MARS,
    # ... extend as needed
}

class ASMConverter:
    def convert(self, file_obj, instrument_type: str) -> dict:
        vendor = VENDOR_MAP.get(instrument_type)
        if not vendor:
            raise ValueError(
                f"Unsupported instrument type: {instrument_type}. "
                f"Supported: {list(VENDOR_MAP.keys())}"
            )
        try:
            return allotrope_from_io(file_obj, vendor)
        except AllotropeConversionError as e:
            raise ValueError(f"Failed to parse file: {e}") from e
```

### Writing a Custom Parser

If LabLink needs to support an instrument not yet in allotropy, follow the
contribution pattern from the repository:

1. Create a new parser under `src/allotropy/parsers/{vendor_name}/`
2. Implement `VendorParser` extending the base parser class
3. Map raw data to the appropriate ASM schema dataclass
4. Add test fixtures with example instrument output files

The library uses a structured pattern:
```
parsers/
└── vendor_name/
    ├── __init__.py
    ├── vendor_name_parser.py      # main parser class
    ├── vendor_name_reader.py      # file reading logic
    └── vendor_name_structure.py   # intermediate data structures
```

---

## 8. Mintlify Docs with FastAPI

### How It Works

FastAPI auto-generates an OpenAPI spec at `/openapi.json`. Mintlify consumes this
spec to produce interactive API documentation with a built-in API playground.

### Setup Steps

**1. Export your OpenAPI spec from FastAPI:**

```python
# scripts/export_openapi.py
import json
from lablink.main import create_app

app = create_app()
spec = app.openapi()

with open("docs/openapi.json", "w") as f:
    json.dump(spec, f, indent=2)
```

Or serve it live: FastAPI automatically serves at `/openapi.json`.

**2. Initialize Mintlify docs:**

```bash
npx mintlify@latest init
```

**3. Configure docs.json (formerly mint.json):**

```json
{
  "$schema": "https://mintlify.com/docs.json",
  "name": "LabLink API Documentation",
  "logo": {
    "dark": "/logo/dark.svg",
    "light": "/logo/light.svg"
  },
  "favicon": "/favicon.svg",
  "colors": {
    "primary": "#0D6EFD",
    "light": "#4A9CFF",
    "dark": "#0050C8"
  },
  "navigation": {
    "tabs": [
      {
        "tab": "Documentation",
        "groups": [
          {
            "group": "Getting Started",
            "pages": ["introduction", "quickstart", "authentication"]
          },
          {
            "group": "Concepts",
            "pages": ["concepts/instruments", "concepts/asm", "concepts/webhooks"]
          },
          {
            "group": "Desktop Agent",
            "pages": ["agent/installation", "agent/configuration", "agent/troubleshooting"]
          }
        ]
      },
      {
        "tab": "API Reference",
        "openapi": "openapi.json"
      },
      {
        "tab": "MCP Tools",
        "groups": [
          {
            "group": "MCP Integration",
            "pages": ["mcp/overview", "mcp/setup", "mcp/tools-reference"]
          }
        ]
      }
    ]
  },
  "api": {
    "baseUrl": "https://api.lablink.example.com",
    "auth": {
      "method": "bearer"
    },
    "playground": {
      "mode": "simple"
    }
  },
  "openapi": "openapi.json"
}
```

**4. Auto-generate API reference pages:**

```bash
npx @mintlify/scraping@latest openapi-file docs/openapi.json -o docs/api-reference
```

This generates one MDX file per endpoint. The scraper also outputs the suggested
navigation structure for your docs.json.

**5. Validate the setup:**

```bash
npx mintlify openapi-check docs/openapi.json
```

**6. Preview locally:**

```bash
npx mintlify dev
```

### CI/CD Integration

Add to your CI pipeline to keep docs in sync:

```yaml
# .github/workflows/docs.yml
name: Update API Docs
on:
  push:
    paths: ["src/lablink/**"]
    branches: [main]

jobs:
  update-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .
      - run: python scripts/export_openapi.py
      - run: npx @mintlify/scraping@latest openapi-file docs/openapi.json -o docs/api-reference
      - run: npx mintlify openapi-check docs/openapi.json
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "docs: auto-update API reference from OpenAPI spec"
          file_pattern: "docs/**"
```

### Tips for Quality Docs

1. **operation_id** matters doubly: it becomes the MCP tool name AND the docs page slug
2. **summary** shows as the page title in Mintlify navigation
3. **description** renders as the page body -- use markdown formatting
4. **response_model** generates the response schema section automatically
5. **Field descriptions** in Pydantic models become parameter docs
6. Add `examples` to Pydantic models for the API playground:

```python
class InstrumentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "SoftMax Pro Plate Reader",
                    "instrument_type": "softmax_pro",
                    "location": "Lab B, Bench 3",
                }
            ]
        }
    )

    name: str = Field(..., description="Human-readable instrument name")
    instrument_type: str = Field(
        ...,
        description="Instrument type key matching a supported parser",
        json_schema_extra={"enum": ["softmax_pro", "envision", "quantstudio"]},
    )
    location: str | None = Field(None, description="Physical location in the lab")
```

---

## Summary: Priority Implementation Order

| Priority | Component | Effort | Impact |
|----------|-----------|--------|--------|
| 1 | FastAPI project structure (domain modules) | 1 day | Foundation for everything |
| 2 | Response envelope + exception handlers | 0.5 day | Consistency for all consumers |
| 3 | OpenAPI optimization (operation_ids, descriptions) | 1 day | Enables agents + docs |
| 4 | Mintlify docs setup | 0.5 day | Developer experience |
| 5 | FastMCP integration | 1 day | Agent-native access |
| 6 | ASM converter integration (allotropy) | 1-2 days | Core value proposition |
| 7 | Webhook/event system | 2 days | Integration with external systems |
| 8 | Go desktop agent | 3-5 days | On-prem file ingestion |

---

## Sources

### FastAPI Project Structure
- https://github.com/zhanymkanov/fastapi-best-practices
- https://fastapi.tiangolo.com/tutorial/bigger-applications/
- https://fastlaunchapi.dev/blog/fastapi-best-practices-production-2026

### FastMCP
- https://gofastmcp.com/integrations/fastapi
- https://github.com/jlowin/fastmcp (PrefectHQ/fastmcp)
- https://www.speakeasy.com/mcp/framework-guides/building-fastapi-server

### OpenAPI for LLM Agents
- https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/plugins-api-schema-best-practices.html
- https://google.github.io/adk-docs/tools-custom/openapi-tools/
- https://www.xano.com/blog/openapi-specification-the-definitive-guide/

### Webhook Patterns
- https://testdriven.io/blog/fastapi-and-celery/
- https://medium.com/@dewasheesh.rana/celery-redis-fastapi-the-ultimate-2025-production-guide

### Go Agent
- https://github.com/fsnotify/fsnotify
- https://github.com/etcd-io/bbolt

### Allotrope / ASM
- https://github.com/Benchling-Open-Source/allotropy
- https://www.benchling.com/blog/open-source-data-standards-allotrope

### Mintlify
- https://www.mintlify.com/docs/api-playground/openapi-setup
- https://www.mintlify.com/blog/steps-to-autogenerate
