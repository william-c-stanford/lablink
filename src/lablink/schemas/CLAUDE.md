# schemas Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `schemas` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Pydantic v2 request/response schemas for LabLink. Defines the API contract — what comes in (Create/Update schemas), what goes out (Response schemas), and the shared infrastructure (Envelope[T], canonical data types). Schemas are also the source of truth for OpenAPI docs and MCP tool descriptions.

## Architecture Within This Module

- `envelope.py` — `Envelope[T]`, `ErrorDetail`, `ResponseMeta`, `PaginationMeta`, `success_response()`, `error_response()`
- `canonical.py` — `ParsedResult`, `MeasurementValue`, `InstrumentSettings` (ASM-compatible)
- One file per API domain (matching router files): `auth.py`, `organizations.py`, `projects.py`, `instruments.py`, `agents.py`, `uploads.py`, `experiments.py`, `campaigns.py`, `webhooks.py`, `audit.py`

Each domain file has:
- `{Entity}Create` — POST request body
- `{Entity}Update` — PATCH request body (all fields Optional)
- `{Entity}Response` — Response schema with `ConfigDict(from_attributes=True)`

## Coding Conventions

- **Pydantic v2**: Use `model_config = ConfigDict(from_attributes=True)` on all Response schemas. Use `Field(description="...")` on all fields — descriptions become OpenAPI docs and MCP tool parameter descriptions.
- **Response schemas have `from_attributes=True`**: Required for `Schema.model_validate(orm_obj)` to work.
- **Create vs Update vs Response**: `Create` has required fields. `Update` has all Optional fields. `Response` mirrors the ORM model. Never mix concerns.
- **No HTTP concerns in schemas**: Schemas know nothing about requests, headers, or status codes.
- **Field descriptions are documentation**: Every field should have a `description=` that would help an agent understand the field's purpose.

## Patterns

**Standard domain schema set**:
```python
# Request schemas (no from_attributes needed)
class ExperimentCreate(BaseModel):
    intent: str = Field(..., description="What this experiment is trying to achieve", max_length=500)
    hypothesis: str | None = Field(None, description="Testable hypothesis, if any")
    campaign_id: uuid.UUID | None = Field(None, description="Optional campaign this belongs to")

class ExperimentUpdate(BaseModel):
    status: ExperimentStatus | None = Field(None, description="New status (follows state machine)")

# Response schema
class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    intent: str
    status: ExperimentStatus
    created_at: datetime
    updated_at: datetime
```

**Envelope usage** (envelope.py):
```python
from lablink.schemas.envelope import success_response, error_response, PaginationMeta

# Success
return success_response(data=ExperimentResponse.model_validate(exp))

# Success with pagination
return success_response(
    data=[ExperimentResponse.model_validate(e) for e in exps],
    pagination=PaginationMeta(total_count=total, page=page, page_size=page_size, has_more=...)
)

# Error (used in exception handlers and error_response() factory)
ErrorDetail(code="EXPERIMENT_NOT_FOUND", message="...", suggestion="Use list_experiments to find valid IDs")
```

**`ParsedResult`** (canonical.py) — output type for all instrument parsers:
```python
@dataclass
class ParsedResult:
    instrument_type: str
    parser_name: str
    measurements: list[MeasurementValue]
    sample_count: int
    settings: InstrumentSettings | None
    raw_metadata: dict
```

## Key Types and Interfaces

- `Envelope[T]` (`envelope.py:63`) — `{ data: T | None, meta: ResponseMeta, errors: list[ErrorDetail] }`
- `ErrorDetail` (`envelope.py:29`) — `code`, `message`, `field`, `suggestion`, `retry`, `retry_after`
- `PaginationMeta` (`envelope.py:21`) — `total_count`, `page`, `page_size`, `has_more`
- `ParsedResult` (`canonical.py`) — Canonical parser output (ASM-compatible)
- `success_response(data, pagination?)` (`envelope.py:95`) — Helper to build `Envelope` responses
- `error_response(code, message, suggestion?, status?)` (`envelope.py:112`) — Builds `JSONResponse` with error `Envelope`

## What Belongs Here

- Pydantic v2 schema classes (Create, Update, Response)
- Shared response infrastructure (Envelope, ErrorDetail, PaginationMeta)
- Canonical data type definitions (ParsedResult, MeasurementValue)
- Field validators and constraints

## What Does Not Belong Here

- ORM model definitions (use `models/`)
- Business logic (use `services/`)
- Database queries (use `services/`)
- Route handler functions (use `routers/`)

## Key Dependencies

- `pydantic` v2 — `BaseModel`, `ConfigDict`, `Field`
- `fastapi.responses.JSONResponse` — only in `envelope.py` for `error_response()`
- No SQLAlchemy imports — schemas are pure Pydantic

## Testing Approach

Schemas are tested implicitly through router tests. If you add a complex `@model_validator` or `@field_validator`, add a unit test in `tests/test_schemas.py`. Test that `from_attributes=True` works by doing `Schema.model_validate(orm_fixture)`.

## Common Gotchas

- **`model_validate()` vs `model_validate(obj, from_attributes=True)`**: With `ConfigDict(from_attributes=True)`, just use `Schema.model_validate(orm_obj)`. The config handles it.
- **UUIDs in schemas vs models**: ORM models store UUIDs as `String(36)`. Pydantic schemas should use `uuid.UUID` (Pydantic auto-converts). Don't use `str` for UUID fields in schemas.
- **`exclude_none=True` in responses**: Routers use `response_model_exclude_none=True` — don't add `None` values to responses that shouldn't be there, but don't try to set them to non-None to force them through.
- **`suggestion` is required for error agents**: Every `ErrorDetail` must have a `suggestion`. It's optional in the type but required in practice for agent recovery.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
