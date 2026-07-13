"""Redis-backed singleton execution guards for periodic upstream polling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress

from django.conf import settings
from redis import Redis
from redis.exceptions import LockError, RedisError


class TaskLockUnavailableError(RuntimeError):
    """Raised when a scheduled task cannot safely acquire its shared Redis lock."""


@contextmanager
def singleton_task_lock(name: str, timeout_seconds: int) -> Iterator[bool]:
    """Yield whether this process owns a bounded, cross-worker task lock."""
    try:
        client = Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)
        lock = client.lock(f"malaysia-transit-live:task:{name}", timeout=timeout_seconds)
        acquired = lock.acquire(blocking=False)
    except RedisError as error:
        raise TaskLockUnavailableError("The Redis task lock is unavailable.") from error

    try:
        yield acquired
    finally:
        if acquired:
            # The expiry protects against a failed worker; a later owner may hold the lock.
            with suppress(LockError):
                lock.release()
