"""Celery tasks for controlled upstream data refreshes."""

from __future__ import annotations

from celery import shared_task

from transit.services.r2_archive import R2ArchiveStore
from transit.services.realtime_poll import poll_realtime_cycle
from transit.services.static_refresh import StaticFeedRefresher
from transit.services.task_lock import TaskLockUnavailableError, singleton_task_lock


@shared_task(name="transit.refresh_static_gtfs")
def refresh_static_gtfs() -> dict[str, int]:
    """Refresh every official static feed serially, at the shared upstream budget."""
    try:
        with singleton_task_lock("static-refresh", timeout_seconds=60 * 60) as acquired:
            if not acquired:
                return {"active": 0, "failed": 0, "skipped": 1}
            results = StaticFeedRefresher(R2ArchiveStore.from_environment()).refresh_all()
    except TaskLockUnavailableError:
        return {"active": 0, "failed": 0, "skipped": 1}
    active_count = sum(result.status == "active" for result in results)
    return {"active": active_count, "failed": len(results) - active_count, "skipped": 0}


@shared_task(name="transit.poll_realtime_vehicle_positions")
def poll_realtime_vehicle_positions() -> dict[str, int]:
    """Poll at most four centrally scheduled realtime feeds during one minute."""
    try:
        with singleton_task_lock("realtime-poll", timeout_seconds=55) as acquired:
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
