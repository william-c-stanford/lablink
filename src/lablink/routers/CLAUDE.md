# routers Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `routers` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Thin FastAPI routers for LabLink's 13 API domains: auth, organizations, projects, instruments, agents, uploads, data, experiments, campaigns, webhooks, audit, admin. Routers are the HTTP interface layer only — they validate input, inject dependencies, call services, and wrap responses in `Envelope[T]`.

## Architecture Within This Module

One file per API domain (plural snake_case matching URL prefix). Each file:
1. Creates an `APIRouter` with `prefix` and `tags`
2. Defines route handler functions that call service functions
3. Returns `success_response(data)` or lets exceptions propagate to the global handler

The router is registered in `main.py` via `app.include_router(router)`.

## Coding Conventions

- **Routers are thin**: No business logic. If a handler is more than ~15 lines of logic, it belongs in a service.
- **`operation_id` on every route**: Use `verb_noun` snake_case (`create_experiment`, `list_uploads`). This becomes the MCP tool name and OpenAPI operationId.
- **`response_model=Envelope[T]`**: Always specify the response model for OpenAPI schema generation.
- **`response_model_exclude_none=True`**: Always set this to keep response payloads clean.
- **Dependency injection via `Depends()`**: `get_db`, `get_current_user`, `get_current_org` are always injected — never instantiate these directly.
- **Validate with schemas, not ad-hoc**: Request bodies use Pydantic schema classes from `schemas/`. Don't parse request data manually.
- **Return `success_response()`**: Always wrap successful data. Never return raw dicts or ORM objects.
- **Status 201 for creation**: `status_code=201` on POST endpoints that create resources.

## Patterns

**Standard endpoint structure** (see `routers/experiments.py` for canonical example):
```python
@router.post(
    "",
    response_model=Envelope[ExperimentResponse],
    status_code=201,
    operation_id="create_experiment",
    response_model_exclude_none=True,
)
async def create_exp(
    body: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    result = await create_experiment(db, organization_id=org.id, ...)
    return success_response(data=ExperimentResponse.model_validate(result))
```

**List endpoints with pagination**:
```python
return success_response(
    data=[Schema.model_validate(item) for item in items],
    pagination=PaginationMeta(total_count=total, page=page, page_size=page_size, has_more=...),
)
```

**Validation errors in handlers** (when service can't do it):
```python
from lablink.exceptions import ValidationError
raise ValidationError(
    message=f"Invalid status '{status}'",
    suggestion=f"Valid statuses: {[s.value for s in SomeEnum]}",
    field="status",
)
```

## Key Types and Interfaces

- `Envelope[T]` (`schemas/envelope.py`) — All responses are wrapped in this
- `success_response(data, pagination?)` (`schemas/envelope.py`) — Factory for success responses
- `PaginationMeta` (`schemas/envelope.py`) — Pagination for list endpoints
- `get_db` (`dependencies.py`) — Async SQLAlchemy session
- `get_current_user` (`dependencies.py`) — Authenticated user or 401
- `get_current_org` (`dependencies.py`) — Current organization (from JWT claims)

## What Belongs Here

- FastAPI route handler functions
- Request body → service call → response wrapping
- Query parameter validation (via `Query(...)`)
- Router-level `prefix` and `tags`

## What Does Not Belong Here

- Business logic (use `services/`)
- Direct ORM queries (use `services/`)
- Complex validation beyond Pydantic schema validation (use `services/`)
- Auth logic (use `dependencies.py`)

## Key Dependencies

- `fastapi` — `APIRouter`, `Depends`, `Query`, `HTTPException`
- `lablink.schemas.envelope` — `Envelope`, `success_response`, `PaginationMeta`
- `lablink.dependencies` — `get_db`, `get_current_user`, `get_current_org`
- `lablink.services.*` — service functions (always imported directly, not the service class)

## Testing Approach

Router tests use `httpx.AsyncClient` with `ASGITransport` against the real FastAPI app with SQLite.
Override dependencies via `app.dependency_overrides` for auth in tests.
Test files in `tests/routers/` or `tests/test_*.py`. Each router should test: happy path, 404, auth required, and invalid input.

## Common Gotchas

- **`model_validate()` not `from_orm()`**: Pydantic v2 uses `Schema.model_validate(orm_obj)`, not `Schema.from_orm(orm_obj)`.
- **Organization scoping**: Every service call must pass `organization_id=org.id`. Forgetting this leaks cross-org data.
- **`operation_id` must be globally unique**: Duplicate operation_ids break OpenAPI spec generation and MCP tool names.
- **UUID path params**: FastAPI auto-validates `uuid.UUID` path params — use `uuid.UUID` type annotation, not `str`.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
