"""Route, stop, trip, and text-search endpoints for active static GTFS versions."""

from __future__ import annotations

from datetime import date

from django.db.models import Q
from ninja import Router
from ninja.errors import HttpError

from transit.http.api_common import (
    active_feed_version,
    route_mode,
    route_search_item,
    stop_search_item,
)
from transit.http.query_helpers import active_versions, is_service_scheduled, source_metadata
from transit.http.schemas import RouteDetail, SearchResponse, StopDetail, TripDetail, TripStop
from transit.models import GtfsRoute, GtfsService, GtfsStop, GtfsStopTime, GtfsTrip

router = Router()
MINIMUM_SEARCH_LENGTH = 2


@router.get("/search", response=SearchResponse)
def search_network(request: object, q: str, limit: int = 20) -> SearchResponse:
    """Search active routes and stops without mixing historical static versions."""
    del request
    query = q.strip()
    if len(query) < MINIMUM_SEARCH_LENGTH:
        raise HttpError(400, "Search query must be at least two characters.")
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
        routes=[route_search_item(route) for route in routes],
        stops=[stop_search_item(stop) for stop in stops],
    )


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
        mode=route_mode(route.route_type),
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
    except (GtfsService.DoesNotExist, GtfsTrip.DoesNotExist) as error:
        raise HttpError(404, "Trip not found in the active static version.") from error
    stop_times = list(GtfsStopTime.objects.filter(trip=trip).order_by("stop_sequence"))
    stop_names = dict(
        GtfsStop.objects.filter(
            feed_version=version,
            stop_id__in=[stop_time.stop_id for stop_time in stop_times],
        ).values_list("stop_id", "name"),
    )
    return TripDetail(
        trip_id=trip.trip_id,
        route_id=trip.route_id,
        headsign=trip.headsign,
        service_date=service_date.isoformat(),
        is_scheduled=is_service_scheduled(service, service_date),
        stops=[
            TripStop(
                sequence=stop_time.stop_sequence,
                stop_id=stop_time.stop_id,
                name=stop_names.get(stop_time.stop_id, stop_time.stop_id),
                arrival_time=stop_time.arrival_time,
                departure_time=stop_time.departure_time,
            )
            for stop_time in stop_times
        ],
        source=source_metadata(feed, version),
    )
