# services Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-09 -->

> Local style guide for the `services` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Business logic for LabLink. Services contain the application's domain intelligence: file upload orchestration, instrument file parsing, experiment state machines, campaign management, webhook delivery, search indexing, and audit trail management. Services are completely independent of HTTP — they receive domain objects, execute logic, and return domain objects.

## Architecture Within This Module

Ten service files, each handling one domain:
- `upload_service.py` — `UploadService` class: file hashing, dedup, storage (S3/local), Upload record creation
- `parser_service.py` — `ParserService` class: orchestrates parsing pipeline (fetch bytes → detect → parse → store ParsedData)
- `auth_service.py` — JWT creation/validation, user authentication
- `organization_service.py` — Org creation, user membership management
- `experiment_service.py` — Experiment CRUD, state machine transitions, upload linking
- `campaign_service.py` — Campaign management, progress aggregation
- `webhook_service.py` — Webhook registration, event dispatch, HMAC-SHA256 signing
- `audit_service.py` — Audit event recording with SHA-256 hash chain
- `search_service.py` — Elasticsearch indexing and querying (with in-memory fallback)
- `export_service.py` — Data export to CSV/JSON/Excel

## Coding Conventions

- **Zero HTTP awareness**: Services never import FastAPI, `Request`, `Response`, or any HTTP types. If a service needs to know about HTTP, it's in the wrong place.
- **Class-based services with `__init__(db)`**: Most services take an `AsyncSession` in `__init__`. Some (like `WebhookService`) are instantiated without args and accept `session` per method call.
- **Raise domain errors, not HTTP errors**: Raise `LabLinkError` subclasses (`NotFoundError`, `ValidationError`, `StateTransitionError`). Never raise `HTTPException`.
- **`await db.flush()` not `commit()`**: Services flush but don't commit. The router/dependency handles transaction management (via `async with session.begin()`).
- **`suggestion` in error messages**: All service errors should include actionable suggestions. E.g., `"Use list_uploads to find valid upload IDs."`.
- **Async throughout**: All service methods are `async def`. No sync DB operations.

## Patterns

**Class-based service** (see `upload_service.py` for canonical example):
```python
class UploadService:
    def __init__(self, db: AsyncSession, storage: StorageBackend | None = None) -> None:
        self.db = db
        self.storage = storage or get_storage_backend()

    async def upload_file(self, file_bytes: bytes, filename: str, ...) -> Upload:
        # Business logic here
        ...
        self.db.add(upload)
        await self.db.flush()  # NOT commit()
        return upload
```

**SQLAlchemy 2.0 queries** (select + execute, not session.query):
```python
from sqlalchemy import select, func

stmt = select(Upload).where(
    Upload.organization_id == organization_id,
    Upload.deleted_at.is_(None),
).order_by(Upload.created_at.desc()).limit(limit).offset(offset)
result = await self.db.execute(stmt)
uploads = result.scalars().all()
```

**State machine transitions** (experiment_service.py):
```python
VALID_TRANSITIONS = {
    ExperimentStatus.planned: [ExperimentStatus.running, ExperimentStatus.cancelled],
    ExperimentStatus.running: [ExperimentStatus.completed, ExperimentStatus.failed, ExperimentStatus.cancelled],
}
if target not in VALID_TRANSITIONS.get(current, []):
    raise StateTransitionError(f"Cannot transition {current} → {target}", suggestion="...")
```

## Key Types and Interfaces

- `UploadService` (`upload_service.py`) — `upload_file()`, `check_duplicate()`, `update_status()`, `download_file()`; also defines `StorageBackend` ABC, `LocalStorageBackend`, `S3StorageBackend`
- `ParserService` (`parser_service.py`) — `parse_upload(upload_id)` → `(ParsedResult, ParsedData)`
- `WebhookService` (`webhook_service.py`) — `dispatch(session, event_type, payload, org_id)` fires matching subscriptions with HMAC-SHA256
- `AuditService` (`audit_service.py`) — append-only audit events with SHA-256 hash chain
- `DuplicateUploadError` (`upload_service.py`) — raised when SHA-256 hash matches existing upload in same org

## What Belongs Here

- Domain logic that would be the same whether called from HTTP, MCP, CLI, or tests
- State machine rules and transition validation
- Storage abstractions (StorageBackend in upload_service.py)
- Cross-entity orchestration (e.g., parse → store → fire webhook → queue index)
- Error classes specific to domain operations

## What Does Not Belong Here

- HTTP request/response handling (use `routers/`)
- Pydantic schema definitions (use `schemas/`)
- ORM model definitions (use `models/`)
- Raw file parsing (use `parsers/`)
- Task scheduling (use `tasks/`)

## Key Dependencies

- `sqlalchemy.ext.asyncio.AsyncSession` — all DB operations
- `lablink.models.*` — ORM models (read/write)
- `lablink.exceptions` — `LabLinkError` hierarchy for domain errors
- `lablink.parsers.*` — called by `ParserService` only
- `lablink.config.get_settings` — for storage backend, Celery config, etc.

## Testing Approach

Services are tested via integration tests that use a real SQLite database (via the `db` fixture in `tests/conftest.py`). No mocking of the database — tests verify real SQL queries and state transitions.

Test files: `tests/test_upload_service.py`, `tests/test_experiment_service.py`, etc. Each service should test: happy path, not-found errors, duplicate detection, state transition validation, and edge cases.

To test storage: use `LocalStorageBackend` with a temp dir (pytest `tmp_path` fixture).

## Common Gotchas

- **`flush()` not `commit()`**: Calling `commit()` in a service breaks transaction management in tests and the request lifecycle. Always `flush()` to make changes visible within the session.
- **`db.get(Model, id)` for PK lookup**: Faster than `select().where(id == ...)` because SQLAlchemy uses the identity map. Use it for single-record fetches by primary key.
- **Organization scoping is not automatic**: You must always filter by `organization_id`. The ORM doesn't enforce this. Missing it is a data leak bug.
- **`StorageBackend` is sync-wrapped async**: The `S3StorageBackend` wraps sync boto3 calls in `async def` methods without `await`. This is acceptable for now but may cause blocking in high-throughput scenarios.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
