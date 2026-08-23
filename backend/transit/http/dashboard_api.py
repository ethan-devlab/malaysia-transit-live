from __future__ import annotations

import base64
from datetime import datetime, timedelta

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from transit.http.api_common import dashboard_mode
from transit.http.query_helpers import active_versions
from transit.http.schemas import (
    DashboardFilters,
    DashboardGeometryCoverage,
    DashboardOption,
    DashboardResponse,
    DashboardSource,
    DashboardSummary,
    DashboardVehicle,
    DashboardVehiclePage,
)
from transit.http.status_api import (
    LIVE_FRESHNESS_SECONDS,
    VEHICLE_RETENTION_SECONDS,
    _latest_successful_fetches,
    _realtime_state,
)
from transit.models import (
    GtfsAgency,
    GtfsRoute,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
    StaticFeedVersion,
    TransitFeed,
    UpstreamFetchAttempt,
    VehicleSnapshot,
)

router = Router()
DASHBOARD_DEFAULT_LIMIT = 100
DASHBOARD_MAX_LIMIT = 500


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError, base64.binascii.Error) as error:
        raise HttpError(422, "Invalid dashboard cursor.") from error
    if offset < 0:
        raise HttpError(422, "Invalid dashboard cursor.")
    return offset


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _option_map(values: set[tuple[str, str]], counts: dict[str, int]) -> list[DashboardOption]:
    return [
        DashboardOption(key=key, label=label, count=counts.get(key, 0))
        for key, label in sorted(values, key=lambda value: value[1].lower())
    ]


def _mode_for_snapshot(snapshot: VehicleSnapshot, routes: dict[tuple[str, str], GtfsRoute]) -> str:
    if snapshot.feed_version_id is None or not snapshot.route_id:
        return "unknown"
    route = routes.get((str(snapshot.feed_version_id), snapshot.route_id))
    return dashboard_mode(route, snapshot.feed.slug)


def _freshness(snapshot: VehicleSnapshot, now: datetime) -> str:
    return (
        "live"
        if snapshot.fetched_at >= now - timedelta(seconds=LIVE_FRESHNESS_SECONDS)
        else "stale"
    )


def _next_scheduled_stops(
    snapshots: list[VehicleSnapshot],
    version_ids: list[object],
    now: datetime,
) -> dict[tuple[str, str], str]:
    trip_keys = {
        (str(snapshot.feed_version_id), snapshot.trip_id)
        for snapshot in snapshots
        if snapshot.feed_version_id and snapshot.trip_id
    }
    if not trip_keys:
        return {}
    trip_ids = [trip_id for _, trip_id in trip_keys]
    trips = list(GtfsTrip.objects.filter(feed_version_id__in=version_ids, trip_id__in=trip_ids))
    trip_lookup = {(str(trip.feed_version_id), trip.trip_id): trip.id for trip in trips}
    stop_times = list(
        GtfsStopTime.objects.filter(trip_id__in=trip_lookup.values())
        .select_related("trip")
        .order_by("trip_id", "stop_sequence")
    )
    stop_ids = {stop_time.stop_id for stop_time in stop_times}
    stops = {
        (str(stop.feed_version_id), stop.stop_id): stop.name
        for stop in GtfsStop.objects.filter(feed_version_id__in=version_ids, stop_id__in=stop_ids)
    }
    current_time = timezone.localtime(now).strftime("%H:%M:%S")
    next_stops: dict[tuple[str, str], str] = {}
    for stop_time in stop_times:
        key = (str(stop_time.trip.feed_version_id), stop_time.trip.trip_id)
        scheduled_time = stop_time.departure_time or stop_time.arrival_time
        if key in next_stops or not scheduled_time or scheduled_time < current_time:
            continue
        stop_name = stops.get((str(stop_time.trip.feed_version_id), stop_time.stop_id))
        if stop_name:
            next_stops[key] = stop_name
    return next_stops


def _geometry_coverage(version: StaticFeedVersion | None) -> DashboardGeometryCoverage:
    if version is None:
        return DashboardGeometryCoverage(
            trip_count=0,
            official_shape_count=0,
            matched_infrastructure_count=0,
            stop_sequence_count=0,
            unavailable_count=0,
            matched_infrastructure_derived_at=None,
        )
    trip_count = int(version.record_counts.get("trips", 0))
    trips_with_shape = int(version.record_counts.get("trips_with_shape", 0))
    orphan_trip_shapes = int(version.record_counts.get("orphan_trip_shapes", 0))
    official_shape_count = max(0, trips_with_shape - orphan_trip_shapes)
    return DashboardGeometryCoverage(
        trip_count=trip_count,
        official_shape_count=official_shape_count,
        matched_infrastructure_count=min(
            max(0, trip_count - official_shape_count),
            int(version.record_counts.get("matched_infrastructure_count", 0)),
        ),
        stop_sequence_count=max(
            0,
            trip_count
            - official_shape_count
            - int(version.record_counts.get("matched_infrastructure_count", 0)),
        ),
        unavailable_count=0,
        matched_infrastructure_derived_at=version.record_counts.get(
            "matched_infrastructure_derived_at"
        ),
    )


@router.get("/dashboard", response=DashboardResponse)
def dashboard(
    request: object,
    mode: str = "all",
    operator: str | None = None,
    region: str | None = None,
    cursor: str | None = None,
    limit: int = DASHBOARD_DEFAULT_LIMIT,
) -> DashboardResponse:
    del request
    allowed_modes = {"all", "bus", "mrt", "lrt", "monorail", "rail", "unknown"}
    if mode not in allowed_modes:
        raise HttpError(422, "Invalid dashboard mode.")
    if limit < 1 or limit > DASHBOARD_MAX_LIMIT:
        raise HttpError(422, f"Dashboard limit must be between 1 and {DASHBOARD_MAX_LIMIT}.")
    offset = _decode_cursor(cursor)
    now = timezone.now()
    feeds = list(TransitFeed.objects.all().order_by("slug"))
    feed_ids = [feed.id for feed in feeds]
    versions = list(active_versions().filter(feed_id__in=feed_ids).order_by("feed_id"))
    versions_by_feed = {version.feed_id: version for version in versions}
    version_ids = [version.id for version in versions]
    routes = list(GtfsRoute.objects.filter(feed_version_id__in=version_ids))
    agencies = list(GtfsAgency.objects.filter(feed_version_id__in=version_ids))
    route_map = {(str(route.feed_version_id), route.route_id): route for route in routes}
    agency_map = {
        (str(agency.feed_version_id), agency.agency_id): agency.name for agency in agencies
    }
    agencies_by_version: dict[str, set[str]] = {}
    for agency in agencies:
        agencies_by_version.setdefault(str(agency.feed_version_id), set()).add(agency.name)
    routes_by_version: dict[str, list[GtfsRoute]] = {}
    for route in routes:
        routes_by_version.setdefault(str(route.feed_version_id), []).append(route)
    snapshot_query = (
        VehicleSnapshot.objects.filter(
            feed_id__in=feed_ids,
            validation_state=VehicleSnapshot.ValidationState.VALIDATED,
            fetched_at__gte=now - timedelta(seconds=VEHICLE_RETENTION_SECONDS),
        )
        .select_related("feed", "feed_version")
        .order_by("feed__slug", "vehicle_id")
    )
    page_snapshots: list[VehicleSnapshot] = []
    feed_vehicle_counts: dict[int, int] = {}
    feed_live_counts: dict[int, int] = {}
    feed_stale_counts: dict[int, int] = {}
    feed_unknown_counts: dict[int, int] = {}
    total_vehicle_count = 0
    total_live_vehicle_count = 0
    total_stale_vehicle_count = 0
    total_unknown_vehicle_count = 0

    source_rows: list[DashboardSource] = []
    vehicle_rows: list[DashboardVehicle] = []
    source_modes: dict[int, set[str]] = {}
    for feed in feeds:
        version = versions_by_feed.get(feed.id)
        version_key = str(version.id) if version else ""
        modes = {
            dashboard_mode(route, feed.slug) for route in routes_by_version.get(version_key, [])
        }
        source_modes[feed.id] = modes
    for snapshot in snapshot_query.iterator(chunk_size=1000):
        snapshot_mode = _mode_for_snapshot(snapshot, route_map)
        if mode != "all" and snapshot_mode != mode:
            continue
        if operator and snapshot.feed.operator_key != operator:
            continue
        if region and snapshot.feed.region_key != region:
            continue
        source_modes.setdefault(snapshot.feed_id, set()).add(snapshot_mode)
        total_vehicle_count += 1
        feed_vehicle_counts[snapshot.feed_id] = feed_vehicle_counts.get(snapshot.feed_id, 0) + 1
        if _freshness(snapshot, now) == "live":
            total_live_vehicle_count += 1
            feed_live_counts[snapshot.feed_id] = feed_live_counts.get(snapshot.feed_id, 0) + 1
        else:
            total_stale_vehicle_count += 1
            feed_stale_counts[snapshot.feed_id] = feed_stale_counts.get(snapshot.feed_id, 0) + 1
        if snapshot_mode == "unknown":
            total_unknown_vehicle_count += 1
            feed_unknown_counts[snapshot.feed_id] = feed_unknown_counts.get(snapshot.feed_id, 0) + 1
        if offset <= total_vehicle_count - 1 < offset + limit:
            page_snapshots.append(snapshot)
    latest_fetches = _latest_successful_fetches()
    next_stops = _next_scheduled_stops(page_snapshots, version_ids, now)
    for snapshot in page_snapshots:
        snapshot_mode = _mode_for_snapshot(snapshot, route_map)
        route = route_map.get((str(snapshot.feed_version_id), snapshot.route_id))
        agency_names = []
        if route and route.agency_id:
            agency_name = agency_map.get((str(snapshot.feed_version_id), route.agency_id))
            if agency_name:
                agency_names.append(agency_name)
        vehicle_rows.append(
            DashboardVehicle(
                feed=snapshot.feed.slug,
                feed_display_name=snapshot.feed.display_name,
                operator_key=snapshot.feed.operator_key or snapshot.feed.slug,
                operator_name=snapshot.feed.operator_name or snapshot.feed.display_name,
                region_key=snapshot.feed.region_key or "unknown",
                region_name=snapshot.feed.region_name or "Unclassified",
                agency_names=agency_names,
                mode=snapshot_mode,
                vehicle_id=snapshot.vehicle_id,
                trip_id=snapshot.trip_id,
                route_id=snapshot.route_id,
                route_name=(route.long_name or route.short_name if route else ""),
                trip_headsign="",
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
                freshness=_freshness(snapshot, now),
                static_version_id=str(snapshot.feed_version_id)
                if snapshot.feed_version_id
                else None,
                next_scheduled_stop=next_stops.get(
                    (str(snapshot.feed_version_id), snapshot.trip_id)
                ),
            ),
        )

    filtered_feeds = [
        feed
        for feed in feeds
        if (not operator or feed.operator_key == operator)
        and (not region or feed.region_key == region)
        and (mode == "all" or mode in source_modes.get(feed.id, set()))
    ]
    for feed in filtered_feeds:
        version = versions_by_feed.get(feed.id)
        source_rows.append(
            DashboardSource(
                feed=feed.slug,
                display_name=feed.display_name,
                operator_key=feed.operator_key or feed.slug,
                operator_name=feed.operator_name or feed.display_name,
                region_key=feed.region_key or "unknown",
                region_name=feed.region_name or "Unclassified",
                agency_names=sorted(agencies_by_version.get(str(version.id), set()))
                if version
                else [],
                modes=sorted(source_modes.get(feed.id, set())),
                static_state="active" if version else "unavailable",
                realtime_state=_realtime_state(
                    feed,
                    has_active_static_version=version is not None,
                    latest_fetches=latest_fetches,
                ),
                last_successful_static_fetch_at=latest_fetches.get(
                    (feed.id, UpstreamFetchAttempt.Kind.STATIC),
                ),
                last_successful_realtime_fetch_at=latest_fetches.get(
                    (feed.id, UpstreamFetchAttempt.Kind.REALTIME),
                ),
                vehicle_count=feed_vehicle_counts.get(feed.id, 0),
                live_vehicle_count=feed_live_counts.get(feed.id, 0),
                stale_vehicle_count=feed_stale_counts.get(feed.id, 0),
                unknown_vehicle_count=feed_unknown_counts.get(feed.id, 0),
                geometry_coverage=_geometry_coverage(version),
            ),
        )
    next_offset = offset + len(vehicle_rows)
    has_more = next_offset < total_vehicle_count
    summary = DashboardSummary(
        feed_count=len(filtered_feeds),
        vehicle_count=total_vehicle_count,
        live_vehicle_count=total_live_vehicle_count,
        stale_vehicle_count=total_stale_vehicle_count,
        unknown_vehicle_count=total_unknown_vehicle_count,
        scheduled_only_feed_count=sum(
            source.realtime_state == "scheduled_only" for source in source_rows
        ),
        unavailable_feed_count=sum(
            source.realtime_state == "unavailable" for source in source_rows
        ),
        awaiting_first_fetch_feed_count=sum(
            source.realtime_state == "awaiting_first_fetch" for source in source_rows
        ),
    )
    operator_options = {
        (feed.operator_key or feed.slug, feed.operator_name or feed.display_name) for feed in feeds
    }
    region_options = {
        (feed.region_key or "unknown", feed.region_name or "Unclassified") for feed in feeds
    }
    mode_options = {
        (mode_key, mode_key.replace("_", " ").title())
        for mode_key in ("bus", "mrt", "lrt", "monorail", "rail", "unknown")
    }
    mode_counts = {
        mode_key: sum(mode_key in source_modes.get(feed.id, set()) for feed in filtered_feeds)
        for mode_key, _ in mode_options
    }
    operator_counts = {
        operator_key: sum(
            (feed.operator_key or feed.slug) == operator_key for feed in filtered_feeds
        )
        for operator_key, _ in operator_options
    }
    region_counts = {
        region_key: sum((feed.region_key or "unknown") == region_key for feed in filtered_feeds)
        for region_key, _ in region_options
    }
    return DashboardResponse(
        generated_at=now,
        filters=DashboardFilters(mode=mode, operator=operator, region=region),
        options={
            "modes": _option_map(mode_options, mode_counts),
            "operators": _option_map(operator_options, operator_counts),
            "regions": _option_map(region_options, region_counts),
        },
        summary=summary,
        sources=source_rows,
        vehicles=DashboardVehiclePage(
            items=vehicle_rows,
            total_count=total_vehicle_count,
            returned_count=len(vehicle_rows),
            next_cursor=_encode_cursor(next_offset) if has_more else None,
            truncated=has_more,
        ),
    )
