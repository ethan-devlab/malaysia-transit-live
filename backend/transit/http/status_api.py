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


@router.get("/data-status", response=list[DataStatus])
def data_status(request: object) -> list[DataStatus]:
    """Expose safe per-feed state for the public freshness interface."""
    del request
    active_versions_by_feed = {
        version.feed_id: version for version in active_versions().only("id", "feed_id")
    }
    latest_fetches = _latest_successful_fetches()
    return [
        DataStatus(
            feed=feed.slug,
            static_state="active"
            if (version := active_versions_by_feed.get(feed.id))
            else "unavailable",
            active_version_id=str(version.id) if version else None,
            last_successful_static_fetch_at=latest_fetches.get(
                (feed.id, UpstreamFetchAttempt.Kind.STATIC),
            ),
            last_successful_realtime_fetch_at=latest_fetches.get(
                (feed.id, UpstreamFetchAttempt.Kind.REALTIME),
            ),
        )
        for feed in TransitFeed.objects.all()
    ]


@router.get("/vehicles", response=list[VehicleLocation])
def vehicle_locations(
    request: object,
    feed: str | None = None,
    limit: int = 100,
) -> list[VehicleLocation]:
    """Return retained, reference-validated positions with explicit freshness state."""
    del request
    now = timezone.now()
    snapshots = VehicleSnapshot.objects.filter(
        validation_state=VehicleSnapshot.ValidationState.VALIDATED,
        fetched_at__gte=now - timedelta(seconds=VEHICLE_RETENTION_SECONDS),
    ).select_related("feed", "feed_version")
    if feed:
        snapshots = snapshots.filter(feed__slug=feed)
    return [
        vehicle_location(snapshot, now)
        for snapshot in snapshots.order_by("-fetched_at")[: max(1, min(limit, 100))]
    ]


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
        UpstreamFetchAttempt.objects.filter(succeeded=True)
        .order_by("feed_id", "kind", "-completed_at")
        .values_list("feed_id", "kind", "completed_at")
    )
    latest: dict[tuple[int, str], datetime] = {}
    for feed_id, kind, completed_at in attempts:
        latest.setdefault((feed_id, kind), completed_at)
    return latest
