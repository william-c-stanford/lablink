# routers Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the FastAPI routers layer.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

13 thin FastAPI routers that expose the LabLink REST API. Each router validates input via Pydantic schemas, calls the appropriate service, and returns an `Envelope[T]` response. Zero business logic lives here.

## Coding Conventions

- Routers are thin: validate → call service → return envelope. No business logic.
- Operation IDs follow `verb_noun` snake_case: `list_experiments`, `create_upload`, `get_instrument_data`.
- Use `Depends(get_current_user)`, `Depends(get_current_org)`, `Depends(require_role(...))` for auth.
- Always return `success_response(data)` or `error_response(errors)` — never return bare dicts.
- Tag routes with the domain name for grouped OpenAPI docs.

## Patterns Used

- **Dependency injection**: Auth, DB session, and org context are injected via `Depends()`. Never resolve these manually in route handlers.
- **Envelope responses**: `response_model=Envelope[SomeResponse]` on every route. HTTP status 200 for success; use `HTTPException` only when the service raises `LabLinkError`.
- **Exception mapping**: The FastAPI app in `main.py` registers exception handlers for `LabLinkError` subclasses. Let exceptions propagate from services — don't catch them in routers.

## What Belongs Here

- FastAPI `APIRouter` instances with route handlers.
- Input parsing and basic request validation (Pydantic does the heavy lifting).
- Calling service methods and mapping results to response schemas.

## What Doesn't Belong Here

- Business logic — that lives in `services/`.
- Database queries — that lives in `services/` (which use the DB session from `Depends(get_db)`).
- Auth logic beyond dependency injection.

## Key Dependencies

- `fastapi` (APIRouter, Depends, HTTPException)
- `lablink.services.*` (one or more services per router)
- `lablink.schemas.*` (request/response schemas)
- `lablink.dependencies` (get_db, get_current_user, get_current_org, require_role)
- `lablink.exceptions` (LabLinkError hierarchy)

## Testing Approach

Test via `httpx.AsyncClient` with `ASGITransport`. Override dependencies with `app.dependency_overrides` for auth. Use the shared test fixtures in `tests/conftest.py`. Every router must have tests for: happy path, auth failure (401/403), not found (404), and validation error (422).

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
