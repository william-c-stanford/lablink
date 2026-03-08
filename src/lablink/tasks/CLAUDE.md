# tasks Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `tasks` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Background task pipeline for LabLink. Orchestrates the async processing that happens after a file is uploaded: parsing instrument data, firing webhooks, and indexing to Elasticsearch. Supports both Celery (production) and inline sync execution (development) via a dispatch abstraction.

## Architecture Within This Module

- `dispatch.py` — `dispatch_task(fn, *args)`: routes to Celery `.delay()` or inline call based on `settings.use_celery`
- `celery_app.py` — Celery app configuration with 3 queues: `parsing`, `webhooks`, `indexing`
- `parse_task.py` — `parse_upload_file(upload_id_str)`: full 8-step parse pipeline
- `webhook_task.py` — `deliver_webhook(delivery_id)`: delivers a single webhook with HMAC-SHA256, retries with backoff
- `index_task.py` — `index_parsed_data(upload_id_str)`: indexes `ParsedData` to Elasticsearch (or in-memory mock)

## Coding Conventions

- **Top-level entry points are sync**: Task functions (`parse_upload_file`, etc.) are sync at the top level because Celery works with sync functions. They bridge to async via `asyncio.run()` or `ThreadPoolExecutor`.
- **Celery registration is conditional**: Tasks are wrapped with `app.task(...)` only if `settings.use_celery` is True (checked at module import). This means the same function works both as a Celery task and a plain callable.
- **Always use `dispatch_task()`**: Never call Celery `.delay()` directly. Always go through `dispatch_task()` which handles the sync fallback.
- **Async pipeline under the hood**: The actual work is in `async def _*_async()` functions called from the sync entry point.
- **Create a new session per task**: Tasks create their own `async_session_factory()` context — they don't share sessions with the request that triggered them.
- **Catch everything at the top level**: The pipeline should never crash the Celery worker. Log and return an error payload instead.

## Patterns

**Sync→Async bridge** (see `parse_task.py`):
```python
def parse_upload_file(upload_id_str: str) -> dict:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Called from within an async context (tests, inline call from router)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _parse_upload_async(upload_id_str)).result()
    else:
        return asyncio.run(_parse_upload_async(upload_id_str))
```

**Conditional Celery registration** (at module bottom):
```python
try:
    settings = get_settings()
    if settings.use_celery:
        from lablink.tasks.celery_app import app
        parse_upload_file = app.task(
            name="lablink.tasks.parse_task.parse_upload_file",
            bind=False,
            max_retries=2,
            default_retry_delay=30,
        )(parse_upload_file)
except Exception:
    pass  # Celery not available — function stays as plain callable
```

**Dispatching a task** (from services or routers):
```python
from lablink.tasks.dispatch import dispatch_task
from lablink.tasks.parse_task import parse_upload_file

dispatch_task(parse_upload_file, str(upload_id))
# In dev (sync mode): runs inline immediately
# In prod (Celery mode): sends to Celery queue
```

## Key Types and Interfaces

- `dispatch_task(fn, *args)` (`dispatch.py`) — Universal task dispatcher. Use this, never `.delay()` directly.
- `parse_upload_file(upload_id_str)` (`parse_task.py`) — Entry point for the full parse pipeline. Returns `dict` with status and parse details.
- `deliver_webhook(delivery_id)` (`webhook_task.py`) — Delivers a single webhook delivery record with retry support.
- `index_parsed_data(upload_id_str)` (`index_task.py`) — Indexes parsed data to Elasticsearch.

## What Belongs Here

- Task entry point functions (sync, Celery-compatible)
- Async pipeline implementations (private `_*_async()` functions)
- Celery app configuration and queue definitions
- The `dispatch_task()` abstraction

## What Does Not Belong Here

- Business logic (use `services/`)
- Database queries (use `services/`)
- HTTP handlers (use `routers/`)
- Parser implementations (use `parsers/`)

## Key Dependencies

- `lablink.tasks.dispatch.dispatch_task` — always use for task scheduling
- `lablink.database.async_session_factory` — tasks create their own sessions
- `lablink.services.*` — tasks delegate to services for business logic
- `celery` — optional; only imported when `settings.use_celery` is True

## Testing Approach

Task tests run in sync mode (set `TASK_BACKEND=sync` or override `settings.use_celery=False`). Test the happy path end-to-end: create an Upload, call `parse_upload_file(str(upload_id))`, verify ParsedData was created and Upload status is `parsed`.

Test parse failures: use a fixture file that will fail parsing, verify Upload status is `parse_failed` and `error_message` is set.

Do NOT test Celery task registration in unit tests — that requires a live Celery broker.

## Common Gotchas

- **Celery tasks receive string IDs, not UUIDs**: JSON serialization requires strings. Always convert `uuid.UUID` to `str` before calling `dispatch_task`. Parse back with `uuid.UUID(id_str)` in the task.
- **Thread pool for already-running loops**: When called from within a running event loop (e.g., during tests), you can't do `asyncio.run()`. Use the `ThreadPoolExecutor` pattern to run in a new thread with its own event loop.
- **Session lifetime**: Tasks must open and close their own sessions. Never try to reuse the request's session across task boundaries.
- **Import `celery_app` lazily**: The Celery app import triggers connection attempts. Always import inside the `if settings.use_celery:` block.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
