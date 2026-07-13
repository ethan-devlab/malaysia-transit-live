"""Query helpers shared by versioned public transit API endpoints."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Final

from django.db.models import QuerySet

from transit.http.schemas import SourceMetadata
from transit.models import GtfsService, StaticFeedVersion, TransitFeed, UpstreamFetchAttempt

EARTH_RADIUS_METRES: Final = 6_371_008.8
METRES_PER_LATITUDE_DEGREE: Final = 111_320.0
WEEKDAY_FIELDS: Final = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def active_versions() -> QuerySet[StaticFeedVersion]:
    """Return every current static snapshot; old snapshots are never query defaults."""
    return StaticFeedVersion.objects.filter(status=StaticFeedVersion.Status.ACTIVE)


def source_metadata(feed: TransitFeed, version: StaticFeedVersion) -> SourceMetadata:
    """Build immutable source provenance without leaking operator credentials."""
    last_fetch = (
        UpstreamFetchAttempt.objects.filter(
            feed=feed,
            kind=UpstreamFetchAttempt.Kind.STATIC,
            succeeded=True,
        )
        .order_by("-completed_at")
        .values_list("completed_at", flat=True)
        .first()
    )
    return SourceMetadata(
        feed=feed.slug,
        freshness="scheduled_only",
        last_successful_fetch_at=last_fetch,
        static_version_id=str(version.id),
    )


def is_service_scheduled(service: GtfsService, service_date: date) -> bool:
    """Resolve calendar and calendar_dates for a single local service date."""
    exception_type = (
        service.exceptions.filter(service_date=service_date)
        .values_list("exception_type", flat=True)
        .first()
    )
    if exception_type is not None:
        return exception_type == 1
    if service.start_date and service_date < service.start_date:
        return False
    if service.end_date and service_date > service.end_date:
        return False
    weekday_field = WEEKDAY_FIELDS[service_date.weekday()]
    return bool(getattr(service, weekday_field))


def haversine_metres(
    origin_latitude: float,
    origin_longitude: float,
    target_latitude: float,
    target_longitude: float,
) -> float:
    """Calculate great-circle distance without requiring PostGIS on Railway."""
    latitude_delta = math.radians(target_latitude - origin_latitude)
    longitude_delta = math.radians(target_longitude - origin_longitude)
    origin_latitude_radians = math.radians(origin_latitude)
    target_latitude_radians = math.radians(target_latitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(origin_latitude_radians)
        * math.cos(target_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(haversine))


def bounding_box(
    latitude: float, longitude: float, radius_metres: float
) -> tuple[float, float, float, float]:
    """Return latitude and longitude bounds for indexed pre-filtering."""
    latitude_delta = radius_metres / METRES_PER_LATITUDE_DEGREE
    longitude_scale = METRES_PER_LATITUDE_DEGREE * max(math.cos(math.radians(latitude)), 0.01)
    longitude_delta = radius_metres / longitude_scale
    return (
        latitude - latitude_delta,
        latitude + latitude_delta,
        longitude - longitude_delta,
        longitude + longitude_delta,
    )


def as_utc(value: datetime | None) -> datetime | None:
    """Retain optional timestamps for Ninja schema serialization."""
    return value
