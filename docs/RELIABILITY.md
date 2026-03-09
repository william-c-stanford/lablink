# Reliability

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-09 -->

> SLOs, error handling patterns, and operational runbooks.

## Service Level Objectives

| Metric | Target |
|---|---|
| Availability | 99.9% |
| p95 response time | < 500ms |
| Error rate | < 0.1% |
| Parse success rate | > 95% per instrument type |

## Error Handling

All errors are structured as `Envelope.errors[]` with `code` (machine-readable), `message` (human-readable), `field` (optional), `suggestion` (agent-actionable), `retry` (bool), and `retry_after` (seconds).

Service errors raise `LabLinkError` subclasses (`NotFound`, `ValidationError`, `StateTransitionError`). The app exception handler in `main.py` converts these to `Envelope` responses.

Never expose raw exception tracebacks in API responses. Log with `logger.exception()`, return structured error.

Parse failures are recoverable — the Upload record transitions to `parse_failed` with an `error_message`, and a `upload.parse_failed` webhook fires. Agents can call `reparse_upload` after fixing the issue.

## Logging

Standard Python `logging` module. Logger names match module paths (e.g., `lablink.services.upload_service`). Structured log lines with upload_id, org_id, status for traceability.

Never log raw file bytes, passwords, or API tokens. Log content hashes (first 12 chars) instead of full hashes.

## Monitoring & Alerting

In production: Celery task failures alert via Redis queue depth. Parse failure rate tracked via `upload.parse_failed` webhook events. Audit trail queryable via `GET /audit` for compliance monitoring.

## Testing

Unit tests: `make test` (pytest, no Docker, SQLite). 1,423 tests across 50 files. E2E tests: `make e2e` (Playwright + headless Chromium, starts API + Vite dev server, runs 29 browser tests). E2E tests are excluded from `make test` via `pytest.mark.e2e`. In CI, E2E runs on main push or on PRs with the `run-e2e` label.

## Runbooks

**Deploy**: Merging to `main` triggers GitHub Actions deploy pipeline. Manually: `make migrate && docker-compose up -d api worker` (dev) or push to ECS via Terraform (prod)
**Re-parse failed uploads**: `POST /uploads/{id}/reparse` or MCP `reparse_upload` tool
**Database migration**: `alembic upgrade head` (runs in new event loop, swaps async→sync driver in `env.py`)
**Reset dev DB**: Delete `lablink.db`, run `alembic upgrade head`

## Failure Modes

| Mode | Behavior |
|---|---|
| Celery unavailable | Tasks run inline (sync fallback via `dispatch_task`) — slower but no data loss |
| Elasticsearch down | Upload/parse still works; search returns empty results; indexing queued for retry |
| S3 unavailable | Upload fails with `UploadError` and `suggestion` for retry; file not stored |
| Parser fails | Upload transitions to `parse_failed`; webhook fires; no data loss; reparseable |
| DB constraint violation | `IntegrityError` mapped to `ValidationError` with field and suggestion |
