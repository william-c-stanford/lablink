"""LabLink task layer — Celery tasks with synchronous inline fallback.

When ``settings.use_celery`` is False (the default for dev/test), all tasks
run inline in the calling process.  When True, tasks are dispatched to
Celery workers via Redis.

Public API::

    from lablink.tasks import dispatch_task
    from lablink.tasks.parse_task import parse_upload_file

    dispatch_task(parse_upload_file, upload_id)
"""

from lablink.tasks.dispatch import dispatch_task

__all__ = ["dispatch_task"]
