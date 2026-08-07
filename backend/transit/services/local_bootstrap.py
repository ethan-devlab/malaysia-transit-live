"""Determine whether a manually started local stack must catch up static GTFS data."""

from __future__ import annotations

from datetime import datetime, time
from typing import Final

from django.utils import timezone

from transit.models import StaticFeedVersion, TransitFeed, UpstreamFetchAttempt

STATIC_REFRESH_TIME: Final = time(hour=4)


def static_refresh_is_due(now: datetime) -> bool:
    """Return whether local startup must queue the missing daily static refresh."""
    feed_ids = set(TransitFeed.objects.values_list("id", flat=True))
    if not feed_ids:
        return False
    active_feed_ids = set(
        StaticFeedVersion.objects.filter(status=StaticFeedVersion.Status.ACTIVE).values_list(
            "feed_id", flat=True
        )
    )
    if active_feed_ids != feed_ids:
        return True

    local_now = timezone.localtime(now)
    if local_now.time() < STATIC_REFRESH_TIME:
        return False
    refresh_cutoff = local_now.replace(
        hour=STATIC_REFRESH_TIME.hour,
        minute=0,
        second=0,
        microsecond=0,
    )
    refreshed_feed_ids = set(
        UpstreamFetchAttempt.objects.filter(
            kind=UpstreamFetchAttempt.Kind.STATIC,
            succeeded=True,
            completed_at__gte=refresh_cutoff,
        ).values_list("feed_id", flat=True)
    )
    return refreshed_feed_ids != feed_ids
