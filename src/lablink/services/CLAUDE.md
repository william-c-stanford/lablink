# services Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the business logic services layer.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

10 service modules containing all business logic for LabLink. Services have zero HTTP awareness — they accept plain Python objects, operate on the database via SQLAlchemy async sessions, and return domain objects or raise `LabLinkError` subclasses.

## Coding Conventions

- Services are async functions or classes. Prefer async functions for stateless operations.
- Accept `AsyncSession` (from `Depends(get_db)` in routers) — never create their own DB sessions.
- Raise `LabLinkError` subclasses (`NotFound`, `Validation`, `StateTransition`) — never raise `HTTPException`.
- Return domain data (ORM model instances or dicts). Routers map to response schemas.
- Keep services independently testable: no FastAPI imports allowed in service files.

## Patterns Used

- **Service functions**: `async def create_upload(db: AsyncSession, org_id: str, ...) -> Upload`
- **Error raising**: `raise LabLinkNotFoundError(resource="Upload", id=upload_id, suggestion="Check the upload_id and try again.")`
- **Audit logging**: Call `audit_service.log_event(...)` for any state-changing operation.
- **Task dispatch**: Call `dispatch_task(parse_task, ...)` — never call Celery tasks directly.
- **Search service**: `search_service.index(...)` / `search_service.search(...)` — ES is eventually consistent.

## What Belongs Here

- All business logic: creation, validation, state transitions, authorization checks.
- Database queries using SQLAlchemy async sessions.
- Calls to external systems (S3, ES, Celery) via adapter functions/tasks.
- Audit event creation for state-changing operations.

## What Doesn't Belong Here

- HTTP request/response handling — that lives in `routers/`.
- ORM model definitions — that lives in `models/`.
- Pydantic schema definitions — that lives in `schemas/`.
- Direct Celery task invocation — use `dispatch_task()` from `tasks/dispatch.py`.

## Key Dependencies

- `sqlalchemy.ext.asyncio` (AsyncSession)
- `lablink.models.*` (ORM models)
- `lablink.exceptions` (LabLinkError hierarchy)
- `lablink.tasks.dispatch` (dispatch_task)
- `lablink.services.audit_service` (log_event — imported by other services)

## Testing Approach

Test services by calling them directly with a real async SQLite session (from `tests/conftest.py`). Do not mock the DB — use the in-memory SQLite backend. Mock external services (S3, ES, Celery) at the service boundary using `unittest.mock`.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
