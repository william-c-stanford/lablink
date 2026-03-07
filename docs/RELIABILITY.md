# Reliability

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> SLOs, error handling patterns, and operational runbooks.

## Service Level Objectives

| Metric | Target |
|---|---|
| Availability | 99.9% |
| p95 API response time | < 500ms |
| Parse job completion | < 30s for files up to 10MB |
| Error rate | < 0.1% |

## Error Handling

- All exceptions map to `LabLinkError` subclasses (`exceptions.py`): `NotFound`, `Validation`, `StateTransition`, etc.
- FastAPI exception handlers in `main.py` convert these to `Envelope` error responses with `suggestion` fields.
- Parser errors use `ParseError` (non-fatal) and are stored on the upload record — parse failure never crashes the API.
- Celery tasks retry with exponential backoff (see `webhook_task.py`).

## Logging

- Structured JSON logging via Python `logging`. Include `request_id` from the `Envelope.meta` on every log line.
- Never log raw file content or PII.
- Log at `INFO` for successful operations, `WARNING` for recoverable errors, `ERROR` for unhandled exceptions.

## Monitoring & Alerting

<!-- TODO: Add monitoring stack (Prometheus/Grafana or Datadog) when moving toward production. -->
- Key metrics to monitor: parse task queue depth, webhook delivery failure rate, API error rate, ES indexing lag.

## Runbooks

- **Dev server**: `make dev` (Docker Compose + uvicorn)
- **Run tests**: `make test` (no Docker needed)
- **DB migrations**: `make migrate`
- **Format/lint**: `make format` / `make lint`

## Failure Modes

| Failure | Behavior |
|---|---|
| Redis unavailable | Tasks fall back to sync execution (`TASK_BACKEND=sync`) |
| Elasticsearch down | Uploads still succeed; search returns empty; indexing retried |
| S3 unavailable | Upload fails gracefully with `suggestion` to retry |
| Parser crash | Upload marked as `failed`; raw file preserved; can be reparsed |
