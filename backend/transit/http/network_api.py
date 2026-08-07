"""Route, stop, trip, and text-search endpoints for active static GTFS versions."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Final

from django.db.models import Q
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from transit.http.api_common import (
    active_feed_version,
    route_mode,
    route_search_item,
    stop_search_item,
)
from transit.http.journeys_api import _matching_scheduled_journeys
from transit.http.query_helpers import active_versions, is_service_scheduled, source_metadata
from transit.http.schemas import (
    RouteDetail,
    SearchResponse,
    StopDetail,
    TripDetail,
    TripGeometry,
    TripStop,
    VehicleLocation,
)
from transit.http.status_api import VEHICLE_RETENTION_SECONDS, vehicle_location
from transit.models import GtfsRoute, GtfsService, GtfsStop, GtfsStopTime, GtfsTrip, VehicleSnapshot
from transit.services.trip_geometry import resolve_trip_geometry

router = Router()
MINIMUM_SEARCH_LENGTH = 2
MAXIMUM_SEARCH_LENGTH = 120
_ROUTE_COLOUR_PATTERN: Final = re.compile(r"^[0-9A-Fa-f]{6}$")


def _route_colour(value: str) -> str:
    return value.upper() if _ROUTE_COLOUR_PATTERN.fullmatch(value) else ""


@router.get("/search", response=SearchResponse)
def search_network(request: object, q: str, limit: int = 20) -> SearchResponse:
    """Search active schedules, network records, and validated positions by one term."""
    del request
    query = q.strip()
    if len(query) < MINIMUM_SEARCH_LENGTH:
        raise HttpError(400, "Search query must be at least two characters.")
    if len(query) > MAXIMUM_SEARCH_LENGTH:
        raise HttpError(400, "Search query must be at most 120 characters.")
    result_limit = max(1, min(limit, 50))
    route_filter = Q(short_name__icontains=query) | Q(long_name__icontains=query)
    routes = (
        GtfsRoute.objects.filter(feed_version__in=active_versions())
        .filter(route_filter)
        .select_related("feed_version__feed")[:result_limit]
    )
    stops = (
        GtfsStop.objects.filter(feed_version__in=active_versions())
        .filter(name__icontains=query)
        .select_related("feed_version__feed")[:result_limit]
    )
    return SearchResponse(
        query=query,
        journeys=_matching_scheduled_journeys(query, timezone.localdate(), result_limit),
        routes=[route_search_item(route) for route in routes],
        stops=[stop_search_item(stop) for stop in stops],
        vehicles=_matching_vehicle_locations(query, result_limit),
    )


def _matching_vehicle_locations(query: str, result_limit: int) -> list[VehicleLocation]:
    now = timezone.now()
    snapshot_filter = (
        Q(vehicle_id__icontains=query)
        | Q(route_id__icontains=query)
        | Q(trip_id__icontains=query)
        | Q(feed__slug__icontains=query)
        | Q(feed__display_name__icontains=query)
    )
    snapshots = (
        VehicleSnapshot.objects.filter(
            validation_state=VehicleSnapshot.ValidationState.VALIDATED,
            fetched_at__gte=now - timedelta(seconds=VEHICLE_RETENTION_SECONDS),
        )
        .filter(snapshot_filter)
        .select_related("feed", "feed_version")
        .order_by("-fetched_at", "feed__slug", "vehicle_id")[:result_limit]
    )
    return [vehicle_location(snapshot, now) for snapshot in snapshots]


@router.get("/routes/{feed_slug}/{route_id}", response=RouteDetail)
def route_detail(request: object, feed_slug: str, route_id: str) -> RouteDetail:
    """Return one current route; journey timings are exposed by the trip endpoint."""
    del request
    feed, version = active_feed_version(feed_slug)
    try:
        route = GtfsRoute.objects.get(feed_version=version, route_id=route_id)
    except GtfsRoute.DoesNotExist as error:
        raise HttpError(404, "Route not found in the active static version.") from error
    return RouteDetail(
        route_id=route.route_id,
        short_name=route.short_name,
        long_name=route.long_name,
        description=route.description,
        mode=route_mode(route.route_type, route.feed_version.feed.slug),
        source=source_metadata(feed, version),
    )


@router.get("/stops/{feed_slug}/{stop_id}", response=StopDetail)
def stop_detail(request: object, feed_slug: str, stop_id: str) -> StopDetail:
    """Return one active stop without exposing prior static versions or upstream URLs."""
    del request
    feed, version = active_feed_version(feed_slug)
    try:
        stop = GtfsStop.objects.get(feed_version=version, stop_id=stop_id)
    except GtfsStop.DoesNotExist as error:
        raise HttpError(404, "Stop not found in the active static version.") from error
    return StopDetail(
        stop_id=stop.stop_id,
        name=stop.name,
        latitude=float(stop.latitude),
        longitude=float(stop.longitude),
        platform_code=stop.platform_code,
        source=source_metadata(feed, version),
    )


@router.get("/trips/{feed_slug}/{trip_id}", response=TripDetail)
def trip_detail(
    request: object,
    feed_slug: str,
    trip_id: str,
    service_date: date,
) -> TripDetail:
    """Return planned GTFS stop times for an explicit service date, never an ETA."""
    del request
    feed, version = active_feed_version(feed_slug)
    try:
        trip = GtfsTrip.objects.get(feed_version=version, trip_id=trip_id)
        service = GtfsService.objects.get(feed_version=version, service_id=trip.service_id)
        route = GtfsRoute.objects.get(feed_version=version, route_id=trip.route_id)
    except (GtfsRoute.DoesNotExist, GtfsService.DoesNotExist, GtfsTrip.DoesNotExist) as error:
        raise HttpError(404, "Trip not found in the active static version.") from error
    stop_times = list(GtfsStopTime.objects.filter(trip=trip).order_by("stop_sequence"))
    stops_by_id = {
        stop_id: (name, float(latitude), float(longitude))
        for stop_id, name, latitude, longitude in GtfsStop.objects.filter(
            feed_version=version,
            stop_id__in=[stop_time.stop_id for stop_time in stop_times],
        ).values_list("stop_id", "name", "latitude", "longitude")
    }
    trip_stops = [
        TripStop(
            sequence=stop_time.stop_sequence,
            stop_id=stop_time.stop_id,
            name=stops_by_id.get(stop_time.stop_id, (stop_time.stop_id, None, None))[0],
            latitude=stops_by_id.get(stop_time.stop_id, ("", None, None))[1],
            longitude=stops_by_id.get(stop_time.stop_id, ("", None, None))[2],
            arrival_time=stop_time.arrival_time,
            departure_time=stop_time.departure_time,
        )
        for stop_time in stop_times
    ]
    geometry = resolve_trip_geometry(
        version,
        trip,
        tuple(
            (stop.longitude, stop.latitude)
            for stop in trip_stops
            if stop.latitude is not None and stop.longitude is not None
        ),
    )
    return TripDetail(
        trip_id=trip.trip_id,
        route_id=trip.route_id,
        headsign=trip.headsign,
        service_date=service_date.isoformat(),
        is_scheduled=is_service_scheduled(service, service_date),
        route_color=_route_colour(route.route_color),
        route_text_color=_route_colour(route.text_color),
        geometry=TripGeometry(
            coordinates=list(geometry.coordinates) if geometry.coordinates is not None else None,
            quality=geometry.quality,
            shape_id=geometry.shape_id,
            source=geometry.source,
            source_version=geometry.source_version,
            attribution=geometry.attribution,
        ),
        stops=trip_stops,
        source=source_metadata(feed, version),
    )
