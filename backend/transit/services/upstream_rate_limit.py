"""Shared, fail-closed upstream request spacing for the official API budget."""

from __future__ import annotations

import time
from uuid import uuid4

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

REQUEST_INTERVAL_SECONDS = 15
MAX_WAIT_SECONDS = 60


class UpstreamRateLimitError(RuntimeError):
    """Raised when a process cannot safely reserve an upstream request slot."""


def wait_for_upstream_slot(scope: str) -> None:
    """Reserve a globally spaced slot, failing closed when Redis is unavailable."""
    client = Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    key = f"malaysia-transit-live:upstream-slot:{scope}"
    token = str(uuid4())

    while time.monotonic() < deadline:
        try:
            if client.set(key, token, nx=True, ex=REQUEST_INTERVAL_SECONDS):
                return
            remaining_seconds = client.ttl(key)
        except RedisError as error:
            raise UpstreamRateLimitError(
                "The shared upstream request gate is unavailable.",
            ) from error

        wait_seconds = 0.25 if remaining_seconds < 1 else min(float(remaining_seconds), 1.0)
        time.sleep(wait_seconds)

    raise UpstreamRateLimitError("The shared upstream request gate did not open in time.")
