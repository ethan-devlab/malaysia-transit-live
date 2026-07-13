"""User-facing data freshness rules."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

_MAXIMUM_LIVE_AGE: Final = timedelta(seconds=90)


class DataStatus(StrEnum):
    """The only public freshness states exposed by the API."""

    LIVE = "live"
    STALE = "stale"
    SCHEDULED_ONLY = "scheduled_only"
    UNAVAILABLE = "unavailable"


def freshness_status(
    *,
    realtime_available: bool,
    last_successful_fetch_at: datetime | None,
    now: datetime,
    maximum_live_age: timedelta = _MAXIMUM_LIVE_AGE,
) -> DataStatus:
    """Classify a feed without inferring an arrival estimate."""
    if not realtime_available:
        return DataStatus.SCHEDULED_ONLY
    if last_successful_fetch_at is None:
        return DataStatus.UNAVAILABLE
    if now - last_successful_fetch_at <= maximum_live_age:
        return DataStatus.LIVE
    return DataStatus.STALE
