"""Celery tasks for controlled upstream data refreshes."""

from __future__ import annotations

from celery import Task, shared_task
from django.conf import settings
from django.utils import timezone

from transit.services.archive_store import archive_store_from_environment
from transit.services.local_bootstrap import static_refresh_is_due
from transit.services.realtime_poll import poll_realtime_cycle
from transit.services.static_import.retention import prune_local_audit_history
from transit.services.static_refresh import StaticFeedRefresher
from transit.services.task_lock import TaskLockUnavailableError, singleton_task_lock

STATIC_REFRESH_RETRY_DELAY_SECONDS = 15 * 60
STATIC_REFRESH_MAX_RETRIES = 3
REALTIME_POLL_LOCK_TIMEOUT_SECONDS = 120


@shared_task(
    bind=True,
    default_retry_delay=STATIC_REFRESH_RETRY_DELAY_SECONDS,
    max_retries=STATIC_REFRESH_MAX_RETRIES,
    name="transit.refresh_static_gtfs",
)
def refresh_static_gtfs(self: Task, retry_feed_slugs: list[str] | None = None) -> dict[str, int]:
    """Refresh every official static feed serially, at the shared upstream budget."""
    try:
        with singleton_task_lock("static-refresh", timeout_seconds=60 * 60) as acquired:
            if not acquired:
                return {"active": 0, "failed": 0, "skipped": 1}
            if settings.LOCAL_ONLY and not static_refresh_is_due(timezone.now()):
                return {"active": 0, "failed": 0, "skipped": 1}
            archive_store = archive_store_from_environment()
            refresher = StaticFeedRefresher(archive_store)
            requested_slugs = tuple(dict.fromkeys(retry_feed_slugs or ()))
            if requested_slugs:
                results = [
                    result
                    for feed_slug in requested_slugs
                    for result in refresher.refresh_all(feed_slug)
                ]
            else:
                results = refresher.refresh_all()
            if settings.LOCAL_ONLY:
                prune_local_audit_history(archive_store)
    except TaskLockUnavailableError:
        return {"active": 0, "failed": 0, "skipped": 1}
    active_count = sum(result.status == "active" for result in results)
    failed_count = len(results) - active_count
    if failed_count:
        failed_feed_slugs = [result.feed_slug for result in results if result.status != "active"]
        raise self.retry(
            exc=RuntimeError(f"{failed_count} official static GTFS feeds failed to refresh."),
            kwargs={"retry_feed_slugs": failed_feed_slugs},
        )
    return {"active": active_count, "failed": 0, "skipped": 0}


@shared_task(name="transit.poll_realtime_vehicle_positions")
def poll_realtime_vehicle_positions() -> dict[str, int]:
    """Poll at most four centrally scheduled realtime feeds during one minute."""
    try:
        with singleton_task_lock(
            "realtime-poll",
            timeout_seconds=REALTIME_POLL_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {
                    "accepted_positions": 0,
                    "deferred_feeds": 0,
                    "failed_feeds": 0,
                    "polled_feeds": 0,
                    "skipped": 1,
                }
            results = poll_realtime_cycle()
    except TaskLockUnavailableError:
        return {
            "accepted_positions": 0,
            "deferred_feeds": 0,
            "failed_feeds": 0,
            "polled_feeds": 0,
            "skipped": 1,
        }
    return {
        "accepted_positions": sum(result.accepted_positions for result in results),
        "deferred_feeds": sum(result.status == "deferred" for result in results),
        "failed_feeds": sum(result.status == "failed" for result in results),
        "polled_feeds": len(results),
        "skipped": 0,
    }
