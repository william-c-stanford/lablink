"""Celery application configuration.

Creates the Celery app instance with three dedicated queues:

- **parsing** — file parsing tasks (CPU-bound, medium priority)
- **webhooks** — outbound webhook delivery (I/O-bound, high priority)
- **indexing** — search index updates (I/O-bound, low priority)

The app is only usable when ``settings.use_celery`` is True and a Redis
broker is reachable.  In sync/dev mode the app object still exists but
tasks are never sent to it — :func:`lablink.tasks.dispatch_task` calls
them inline instead.

Usage::

    # Start a worker:
    celery -A lablink.tasks.celery_app worker -l info -Q parsing,webhooks,indexing
"""

from __future__ import annotations

from celery import Celery

from lablink.config import get_settings

settings = get_settings()

app = Celery(
    "lablink",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# ── Celery configuration ──────────────────────────────────────────────────

app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Queue routing
    task_default_queue="parsing",
    task_queues={
        "parsing": {
            "exchange": "parsing",
            "routing_key": "parsing",
        },
        "webhooks": {
            "exchange": "webhooks",
            "routing_key": "webhooks",
        },
        "indexing": {
            "exchange": "indexing",
            "routing_key": "indexing",
        },
    },
    # Task routing — map task names to queues
    task_routes={
        "lablink.tasks.parse_task.parse_upload_file": {"queue": "parsing"},
        "lablink.tasks.webhook_task.deliver_webhook": {"queue": "webhooks"},
        "lablink.tasks.index_task.index_parsed_data": {"queue": "indexing"},
    },
    # Retry / reliability
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Result expiry (24 hours)
    result_expires=86400,
)

# Auto-discover tasks in the lablink.tasks package
app.autodiscover_tasks(["lablink.tasks"])
