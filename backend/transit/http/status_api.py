"""Public freshness and validated-vehicle endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone
from ninja import Router

from transit.http.query_helpers import active_versions
from transit.http.schemas import DataStatus, VehicleLocation
from transit.models import TransitFeed, UpstreamFetchAttempt, VehicleSnapshot

router = Router()

LIVE_FRESHNESS_SECONDS = 90
VEHICLE_RETENTION_SECONDS = 15 * 60
VEHICLE_SNAPSHOT_LIMIT = 100
VEHICLE_SNAPSHOT_PER_FEED_LIMIT = 7


@router.get("/data-status", response=list[DataStatus])
def data_status(request: object) -> list[DataStatus]:
    """Expose safe per-feed state for the public freshness interface."""
    del request
    active_versions_by_feed = {
        version.feed_id: version for version in active_versions().only("id", "feed_id")
    }
    latest_fetches = _latest_successful_fetches()
    statuses: list[DataStatus] = []
    for feed in TransitFeed.objects.all():
        version = active_versions_by_feed.get(feed.id)
        statuses.append(
            DataStatus(
                feed=feed.slug,
                static_state="active" if version else "unavailable",
                realtime_state=_realtime_state(
                    feed,
                    has_active_static_version=version is not None,
                    latest_fetches=latest_fetches,
                ),
                active_version_id=str(version.id) if version else None,
                last_successful_static_fetch_at=latest_fetches.get(
                    (feed.id, UpstreamFetchAttempt.Kind.STATIC),
                ),
                last_successful_realtime_fetch_at=latest_fetches.get(
                    (feed.id, UpstreamFetchAttempt.Kind.REALTIME),
                ),
            ),
        )
    return statuses


@router.get("/vehicles", response=list[VehicleLocation])
def vehicle_locations(
    request: object,
    feed: str | None = None,
    limit: int = 100,
) -> list[VehicleLocation]:
    """Return retained, reference-validated positions with explicit freshness state."""
    del request
    now = timezone.now()
    return [
        vehicle_location(snapshot, now)
        for snapshot in _recent_validated_vehicle_snapshots(now, feed=feed, limit=limit)
    ]


def _recent_validated_vehicle_snapshots(
    now: datetime,
    *,
    feed: str | None = None,
    limit: int = VEHICLE_SNAPSHOT_LIMIT,
) -> list[VehicleSnapshot]:
    capped_limit = max(1, min(limit, VEHICLE_SNAPSHOT_LIMIT))
    snapshots = VehicleSnapshot.objects.filter(
        validation_state=VehicleSnapshot.ValidationState.VALIDATED,
        fetched_at__gte=now - timedelta(seconds=VEHICLE_RETENTION_SECONDS),
    ).select_related("feed", "feed_version")
    if feed:
        return list(
            snapshots.filter(feed__slug=feed).order_by("-fetched_at", "vehicle_id")[:capped_limit],
        )

    selected: list[VehicleSnapshot] = []
    per_feed_counts: dict[int, int] = {}
    ordered_snapshots = snapshots.order_by(
        "-feed__realtime_priority",
        "feed__slug",
        "-fetched_at",
        "vehicle_id",
    )
    for snapshot in ordered_snapshots.iterator(chunk_size=500):
        count = per_feed_counts.get(snapshot.feed_id, 0)
        if count >= VEHICLE_SNAPSHOT_PER_FEED_LIMIT:
            continue
        per_feed_counts[snapshot.feed_id] = count + 1
        selected.append(snapshot)
        if len(selected) >= capped_limit:
            break
    return selected[:capped_limit]


def vehicle_location(snapshot: VehicleSnapshot, now: datetime) -> VehicleLocation:
    """Serialize a snapshot without promoting stale data to verified live state."""
    freshness = (
        "live"
        if snapshot.fetched_at >= now - timedelta(seconds=LIVE_FRESHNESS_SECONDS)
        else "stale"
    )
    return VehicleLocation(
        feed=snapshot.feed.slug,
        vehicle_id=snapshot.vehicle_id,
        trip_id=snapshot.trip_id,
        route_id=snapshot.route_id,
        latitude=float(snapshot.latitude),
        longitude=float(snapshot.longitude),
        bearing=float(snapshot.bearing) if snapshot.bearing is not None else None,
        speed_metres_per_second=(
            float(snapshot.speed_metres_per_second)
            if snapshot.speed_metres_per_second is not None
            else None
        ),
        position_reported_at=snapshot.position_reported_at,
        fetched_at=snapshot.fetched_at,
        freshness=freshness,
        static_version_id=str(snapshot.feed_version_id) if snapshot.feed_version_id else None,
    )


def _latest_successful_fetches() -> dict[tuple[int, str], datetime]:
    """Collect each feed/kind timestamp once rather than issuing per-feed lookup queries."""
    attempts = (
        UpstreamFetchAttempt.objects.filter(
            succeeded=True,
            completed_at__gte=timezone.now() - timedelta(days=7),
        )
        .order_by("feed_id", "kind", "-completed_at")
        .values_list("feed_id", "kind", "completed_at")
    )
    latest: dict[tuple[int, str], datetime] = {}
    for feed_id, kind, completed_at in attempts:
        latest.setdefault((feed_id, kind), completed_at)
    return latest


def _realtime_state(
    feed: TransitFeed,
    *,
    has_active_static_version: bool,
    latest_fetches: dict[tuple[int, str], datetime],
) -> str:
    if not has_active_static_version:
        return "unavailable"
    if not feed.is_realtime_enabled or not feed.realtime_source_url:
        return "scheduled_only"
    if (feed.id, UpstreamFetchAttempt.Kind.REALTIME) in latest_fetches:
        return "available"
    return "awaiting_first_fetch"
