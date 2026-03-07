# tasks Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the Celery task layer.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

Celery task definitions for async processing: parse uploaded files (`parse_task`), deliver webhooks with HMAC-SHA256 and retry backoff (`webhook_task`), and index parsed data to Elasticsearch (`index_task`). All tasks support a sync fallback via `dispatch_task()` when `TASK_BACKEND=sync`.

## Coding Conventions

- Never invoke Celery tasks directly (`task.delay()`). Always use `dispatch_task(task_fn, ...)` from `dispatch.py`.
- Tasks must be idempotent — they may be retried on failure.
- Tasks should not raise unhandled exceptions. Log errors and update the upload/delivery record's status instead.
- Keep task functions thin: fetch data, call service logic, update status.

## Patterns Used

- **dispatch_task()**: `tasks/dispatch.py` — calls `.delay()` when `TASK_BACKEND=celery`, runs inline when `TASK_BACKEND=sync`. Use this exclusively.
- **parse_task flow**: load upload → detect format → parse → store `ParsedResult` in PG → update upload status → `dispatch_task(webhook_task)` → `dispatch_task(index_task)`.
- **webhook_task**: HMAC-SHA256 signing, exponential backoff retry (Celery `autoretry_for` + `max_retries`), records delivery status to `webhook_delivery` table.
- **index_task**: calls `search_service.index()`. Failure is non-fatal — ES is eventually consistent.

## What Belongs Here

- Celery task function definitions (decorated with `@celery_app.task`).
- `dispatch_task()` — the only entry point for triggering tasks.
- `celery_app.py` — Celery configuration (broker URL, queues: parsing, webhooks, indexing).

## What Doesn't Belong Here

- Business logic beyond orchestration — call services (`upload_service`, `webhook_service`, `search_service`).
- Direct Celery task invocation from routers or services — always go through `dispatch_task()`.

## Key Dependencies

- `celery` (task decorator, app config)
- `lablink.services.*` (upload_service, webhook_service, search_service, parser_service)
- `lablink.config` (TASK_BACKEND, CELERY_BROKER_URL settings)

## Testing Approach

Tests run with `TASK_BACKEND=sync` — tasks execute inline, no broker needed. Test the full pipeline (upload → parse → index) via the upload service tests. For retry behavior, mock `dispatch_task` and assert it was called with the right arguments.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
