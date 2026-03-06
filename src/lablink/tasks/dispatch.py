"""Task dispatcher — routes work to Celery or runs inline.

The single public helper :func:`dispatch_task` checks
``settings.use_celery`` and either calls the function directly (sync
fallback) or sends it to a Celery worker via ``.delay()``.
"""

from __future__ import annotations

import logging
from typing import Any

from lablink.config import get_settings

logger = logging.getLogger(__name__)


def dispatch_task(task_func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run *task_func* inline if sync mode, else dispatch to Celery.

    Parameters
    ----------
    task_func:
        A Celery task (decorated with ``@app.task``) **or** a plain
        callable when running in sync mode.
    *args, **kwargs:
        Positional and keyword arguments forwarded to the task.

    Returns
    -------
    Any
        The task return value (sync) or an ``AsyncResult`` (Celery).
    """
    settings = get_settings()

    if not settings.use_celery:
        logger.debug("Sync dispatch: %s(*%r)", task_func.__name__, args)
        return task_func(*args, **kwargs)

    logger.debug("Celery dispatch: %s.delay(*%r)", task_func.__name__, args)
    return task_func.delay(*args, **kwargs)
