# schemas Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the Pydantic v2 schemas layer.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

Pydantic v2 request/response schemas for all LabLink API endpoints. Includes the universal `Envelope[T]` response wrapper, canonical `ParsedResult` schema, and per-domain Create/Update/Response schema trios.

## Coding Conventions

- Use Pydantic v2 (`model_config = ConfigDict(from_attributes=True)`) on all ORM-backed response schemas.
- Every field must have a `Field(description="...")` — descriptions become OpenAPI docs and MCP tool descriptions.
- Schema names follow the pattern: `{Domain}Create`, `{Domain}Update`, `{Domain}Response`, `{Domain}ListResponse`.
- All endpoints return `Envelope[T]`. Use `success_response(data)` and `error_response(errors)` helpers from `envelope.py`.

## Patterns Used

- **Envelope**: `Envelope[T]` in `envelope.py` wraps every response: `{ data, meta, errors }`. Never return bare dicts.
- **ErrorDetail**: includes `code` (machine-readable), `message` (human), `field` (optional), `suggestion` (agent-actionable), `retry` + `retry_after`.
- **Canonical schema**: `ParsedResult`, `MeasurementValue`, `InstrumentSettings` in `canonical.py` — ASM-compatible output from parsers.
- **Pagination**: `PaginationMeta` in `envelope.py` for list endpoints.

## What Belongs Here

- Pydantic input/output schemas for each domain.
- The `Envelope[T]` definition and helpers.
- The canonical `ParsedResult` and measurement schemas used by parsers.
- Any schema-level validators (`@field_validator`, `@model_validator`).

## What Doesn't Belong Here

- SQLAlchemy models — those live in `models/`.
- Business logic — that lives in `services/`.
- Router logic — that lives in `routers/`.

## Key Dependencies

- `pydantic` v2
- `lablink.models` (for `from_attributes=True` ORM mapping)

## Testing Approach

Schemas are tested implicitly via router/API tests. For complex validators, add unit tests in `tests/test_schemas/`.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
