"""Central, bounded polling and validation of GTFS Realtime vehicle positions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx2
from django.utils import timezone
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from transit.models import (
    GtfsRoute,
    GtfsTrip,
    StaticFeedVersion,
    TransitFeed,
    UpstreamFetchAttempt,
    VehicleSnapshot,
)
from transit.services.upstream_rate_limit import UpstreamRateLimitError, wait_for_upstream_slot

MALAYSIA_LATITUDE_RANGE = (0.8, 7.8)
MALAYSIA_LONGITUDE_RANGE = (98.0, 120.0)
REALTIME_TIMEOUT_SECONDS = 20.0
MAX_REALTIME_BODY_BYTES = 5 * 1024 * 1024
HTTP_OK = 200


@dataclass(frozen=True)
class RealtimePollResult:
    """Safe, aggregate outcome for one upstream GTFS Realtime request."""

    feed_slug: str
    accepted_positions: int
    rejected_positions: int
    status: str


class RealtimeFetchError(ValueError):
    """A bounded, redacted upstream response failure."""

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code


def select_realtime_feeds(cycle_index: int) -> list[TransitFeed]:
    """Use three KL-priority tokens and rotate every other eligible feed in token four."""
    active_feed_ids = StaticFeedVersion.objects.filter(
        status=StaticFeedVersion.Status.ACTIVE,
    ).values_list("feed_id", flat=True)
    eligible = list(
        TransitFeed.objects.filter(
            id__in=active_feed_ids,
            is_realtime_enabled=True,
        )
        .exclude(realtime_source_url="")
        .order_by("realtime_priority", "slug"),
    )
    priorities = [feed for feed in eligible if feed.realtime_priority > 0][:3]
    rotating = [feed for feed in eligible if feed.realtime_priority == 0]
    if not rotating:
        return priorities
    return [*priorities, rotating[cycle_index % len(rotating)]]


def poll_realtime_cycle(cycle_index: int | None = None) -> list[RealtimePollResult]:
    """Poll no more than four validated vehicle-position feeds for one minute cycle."""
    current_cycle = cycle_index if cycle_index is not None else int(time.time() // 60)
    return [poll_realtime_feed(feed) for feed in select_realtime_feeds(current_cycle)]


def poll_realtime_feed(feed: TransitFeed) -> RealtimePollResult:
    """Fetch one protobuf feed, validate references, and retain only latest snapshots."""
    started_at = timezone.now()
    started_monotonic = time.monotonic()
    try:
        wait_for_upstream_slot("gtfs-realtime")
        body = _download_realtime_body(feed.realtime_source_url)
        protobuf = gtfs_realtime_pb2.FeedMessage()
        protobuf.ParseFromString(body)
        accepted, rejected = _store_vehicle_entities(feed, protobuf, timezone.now())
    except UpstreamRateLimitError:
        return RealtimePollResult(feed.slug, 0, 0, "deferred")
    except (DecodeError, httpx2.HTTPError, ValueError) as error:
        return _failed_fetch(
            feed,
            started_at,
            started_monotonic,
            getattr(error, "status_code", None),
        )

    _record_fetch(feed, started_at, started_monotonic, succeeded=True, status_code=200)
    return RealtimePollResult(feed.slug, accepted, rejected, "ok")


def _download_realtime_body(source_url: str) -> bytes:
    """Read a bounded protobuf response before parsing it in memory."""
    body = bytearray()
    with httpx2.stream(
        "GET",
        source_url,
        follow_redirects=False,
        headers={"Accept": "application/x-protobuf, application/octet-stream"},
        timeout=REALTIME_TIMEOUT_SECONDS,
    ) as response:
        if response.status_code != HTTP_OK:
            raise RealtimeFetchError(
                "Official realtime source returned an unsuccessful response.",
                response.status_code,
            )
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_REALTIME_BODY_BYTES:
                raise RealtimeFetchError("Official realtime response exceeded the body limit.")
    if not body:
        raise RealtimeFetchError("Official realtime source returned an empty body.")
    return bytes(body)


def _store_vehicle_entities(
    feed: TransitFeed,
    protobuf: gtfs_realtime_pb2.FeedMessage,
    fetched_at: datetime,
) -> tuple[int, int]:
    version = StaticFeedVersion.objects.filter(
        feed=feed,
        status=StaticFeedVersion.Status.ACTIVE,
    ).first()
    if version is None:
        return 0, 0
    trip_ids = set(GtfsTrip.objects.filter(feed_version=version).values_list("trip_id", flat=True))
    route_ids = set(
        GtfsRoute.objects.filter(feed_version=version).values_list("route_id", flat=True),
    )
    accepted = 0
    rejected = 0
    for entity in protobuf.entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle
        if not vehicle.HasField("position"):
            rejected += 1
            continue
        vehicle_id = vehicle.vehicle.id or entity.id
        if not vehicle_id:
            rejected += 1
            continue
        trip_id = vehicle.trip.trip_id if vehicle.HasField("trip") else ""
        route_id = vehicle.trip.route_id if vehicle.HasField("trip") else ""
        state = _validation_state(feed.slug, trip_id, route_id, trip_ids, route_ids, vehicle)
        _upsert_snapshot(feed, version, vehicle_id, trip_id, route_id, vehicle, fetched_at, state)
        if state == VehicleSnapshot.ValidationState.VALIDATED:
            accepted += 1
        else:
            rejected += 1
    return accepted, rejected


def _validation_state(
    feed_slug: str,
    trip_id: str,
    route_id: str,
    trip_ids: set[str],
    route_ids: set[str],
    vehicle: gtfs_realtime_pb2.VehiclePosition,
) -> str:
    latitude = vehicle.position.latitude
    longitude = vehicle.position.longitude
    if not _is_in_malaysia(latitude, longitude):
        return VehicleSnapshot.ValidationState.OUT_OF_COVERAGE
    if _has_known_reference(feed_slug, trip_id, route_id, trip_ids, route_ids):
        return VehicleSnapshot.ValidationState.VALIDATED
    return VehicleSnapshot.ValidationState.ORPHAN_REFERENCE


def _upsert_snapshot(
    feed: TransitFeed,
    version: StaticFeedVersion,
    vehicle_id: str,
    trip_id: str,
    route_id: str,
    vehicle: gtfs_realtime_pb2.VehiclePosition,
    fetched_at: datetime,
    validation_state: str,
) -> None:
    position = vehicle.position
    reported_at = datetime.fromtimestamp(vehicle.timestamp, UTC) if vehicle.timestamp else None
    VehicleSnapshot.objects.update_or_create(
        feed=feed,
        vehicle_id=vehicle_id,
        defaults={
            "feed_version": version,
            "trip_id": trip_id,
            "route_id": route_id,
            "latitude": Decimal(str(position.latitude)),
            "longitude": Decimal(str(position.longitude)),
            "bearing": Decimal(str(position.bearing)) if position.HasField("bearing") else None,
            "speed_metres_per_second": (
                Decimal(str(position.speed)) if position.HasField("speed") else None
            ),
            "position_reported_at": reported_at,
            "fetched_at": fetched_at,
            "validation_state": validation_state,
        },
    )


def _has_known_reference(
    feed_slug: str,
    trip_id: str,
    route_id: str,
    trip_ids: set[str],
    route_ids: set[str],
) -> bool:
    if route_id and route_id in route_ids:
        return True
    if trip_id in trip_ids:
        return True
    return feed_slug == "rapid-bus-penang" and any(
        static_trip_id.endswith(trip_id) for static_trip_id in trip_ids
    )


def _is_in_malaysia(latitude: float, longitude: float) -> bool:
    return (
        MALAYSIA_LATITUDE_RANGE[0] <= latitude <= MALAYSIA_LATITUDE_RANGE[1]
        and MALAYSIA_LONGITUDE_RANGE[0] <= longitude <= MALAYSIA_LONGITUDE_RANGE[1]
    )


def _failed_fetch(
    feed: TransitFeed,
    started_at: datetime,
    started_monotonic: float,
    status_code: int | None,
) -> RealtimePollResult:
    _record_fetch(feed, started_at, started_monotonic, succeeded=False, status_code=status_code)
    return RealtimePollResult(feed.slug, 0, 0, "failed")


def _record_fetch(
    feed: TransitFeed,
    started_at: datetime,
    started_monotonic: float,
    *,
    succeeded: bool,
    status_code: int | None,
) -> None:
    UpstreamFetchAttempt.objects.create(
        feed=feed,
        kind=UpstreamFetchAttempt.Kind.REALTIME,
        succeeded=succeeded,
        status_code=status_code,
        duration_ms=max(0, round((time.monotonic() - started_monotonic) * 1_000)),
        started_at=started_at,
        completed_at=timezone.now(),
    )
