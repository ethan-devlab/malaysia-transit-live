"""Scheduled-journey and nearby-stop endpoints for active GTFS versions."""

from __future__ import annotations

from datetime import date

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from transit.http.api_common import route_mode
from transit.http.query_helpers import (
    active_versions,
    bounding_box,
    haversine_metres,
    is_service_scheduled,
    source_metadata,
)
from transit.http.schemas import NearbyStop, ScheduledJourney
from transit.models import GtfsRoute, GtfsService, GtfsStop, GtfsStopTime, GtfsTrip

router = Router()

MIN_LATITUDE = -90
MAX_LATITUDE = 90
MIN_LONGITUDE = -180
MAX_LONGITUDE = 180


@router.get("/journeys", response=list[ScheduledJourney])
def scheduled_journeys(
    request: object,
    service_date: date | None = None,
    limit: int = 20,
) -> list[ScheduledJourney]:
    """Return bounded GTFS journey cards for a local service date, never inferred ETAs."""
    del request
    target_date = service_date or timezone.localdate()
    result_limit = max(1, min(limit, 50))
    trips = list(
        GtfsTrip.objects.filter(feed_version__in=active_versions())
        .select_related("feed_version__feed")
        .order_by("feed_version__feed__realtime_priority", "route_id", "trip_id")[
            : result_limit * 8
        ],
    )
    services = {
        (service.feed_version_id, service.service_id): service
        for service in GtfsService.objects.filter(
            feed_version__in=active_versions(),
            service_id__in=[trip.service_id for trip in trips],
        ).prefetch_related("exceptions")
    }
    routes = {
        (route.feed_version_id, route.route_id): route
        for route in GtfsRoute.objects.filter(
            feed_version__in=active_versions(),
            route_id__in=[trip.route_id for trip in trips],
        )
    }
    stop_times_by_trip = _stop_times_by_trip(trips)
    stop_names = _stop_names(trips, stop_times_by_trip)

    journeys: list[ScheduledJourney] = []
    for trip in trips:
        service = services.get((trip.feed_version_id, trip.service_id))
        route = routes.get((trip.feed_version_id, trip.route_id))
        stop_times = stop_times_by_trip.get(trip.id, [])
        if (
            not service
            or not route
            or not stop_times
            or not is_service_scheduled(service, target_date)
        ):
            continue
        first_stop, last_stop = stop_times[0], stop_times[-1]
        journeys.append(
            ScheduledJourney(
                feed=trip.feed_version.feed.slug,
                trip_id=trip.trip_id,
                route_id=trip.route_id,
                mode=route_mode(route.route_type),
                route_label=route.short_name or route.long_name or route.route_id,
                route_name=route.long_name,
                origin=stop_names.get(
                    (trip.feed_version_id, first_stop.stop_id),
                    first_stop.stop_id,
                ),
                destination=stop_names.get(
                    (trip.feed_version_id, last_stop.stop_id),
                    last_stop.stop_id,
                ),
                service_date=target_date.isoformat(),
                planned_start=first_stop.departure_time or first_stop.arrival_time,
                planned_end=last_stop.arrival_time or last_stop.departure_time,
                stop_count=len(stop_times),
                source=source_metadata(trip.feed_version.feed, trip.feed_version),
            ),
        )
        if len(journeys) == result_limit:
            break
    return journeys


@router.get("/stops/nearby", response=list[NearbyStop])
def nearby_stops(
    request: object,
    latitude: float,
    longitude: float,
    radius_metres: int = 750,
    limit: int = 20,
) -> list[NearbyStop]:
    """Use indexed coordinates and Haversine distance instead of a PostGIS dependency."""
    del request
    if (
        not MIN_LATITUDE <= latitude <= MAX_LATITUDE
        or not MIN_LONGITUDE <= longitude <= MAX_LONGITUDE
    ):
        raise HttpError(400, "Coordinates are out of range.")
    bounded_radius = max(50, min(radius_metres, 10_000))
    result_limit = max(1, min(limit, 50))
    min_latitude, max_latitude, min_longitude, max_longitude = bounding_box(
        latitude,
        longitude,
        bounded_radius,
    )
    candidates = GtfsStop.objects.filter(
        feed_version__in=active_versions(),
        latitude__range=(min_latitude, max_latitude),
        longitude__range=(min_longitude, max_longitude),
    ).select_related("feed_version__feed")
    matching_stops = []
    for stop in candidates:
        distance_metres = round(
            haversine_metres(latitude, longitude, float(stop.latitude), float(stop.longitude)),
        )
        if distance_metres <= bounded_radius:
            matching_stops.append((distance_metres, stop))
    matching_stops.sort(key=lambda item: item[0])
    return [
        NearbyStop(
            stop_id=stop.stop_id,
            name=stop.name,
            latitude=float(stop.latitude),
            longitude=float(stop.longitude),
            distance_metres=distance_metres,
            source=source_metadata(stop.feed_version.feed, stop.feed_version),
        )
        for distance_metres, stop in matching_stops[:result_limit]
    ]


def _stop_times_by_trip(trips: list[GtfsTrip]) -> dict[int, list[GtfsStopTime]]:
    stop_times_by_trip: dict[int, list[GtfsStopTime]] = {}
    for stop_time in GtfsStopTime.objects.filter(trip__in=trips).order_by(
        "trip_id",
        "stop_sequence",
    ):
        stop_times_by_trip.setdefault(stop_time.trip_id, []).append(stop_time)
    return stop_times_by_trip


def _stop_names(
    trips: list[GtfsTrip],
    stop_times_by_trip: dict[int, list[GtfsStopTime]],
) -> dict[tuple[object, str], str]:
    stop_ids = [
        stop_time.stop_id for stop_times in stop_times_by_trip.values() for stop_time in stop_times
    ]
    return {
        (stop.feed_version_id, stop.stop_id): stop.name
        for stop in GtfsStop.objects.filter(
            feed_version_id__in=[trip.feed_version_id for trip in trips],
            stop_id__in=stop_ids,
        )
    }
