"""Scheduled-journey and nearby-stop endpoints for active GTFS versions."""

from __future__ import annotations

from datetime import date

from django.db.models import Q
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
ROUTE_SAMPLE_LIMIT = 80
KL_FIRST_FEED_ORDER = {
    "rapid-rail-kl": 0,
    "rapid-bus-kl": 1,
    "rapid-bus-mrtfeeder": 2,
    "ktmb": 3,
}
PRIORITY_MODES = ("metro", "tram", "monorail", "rail", "bus")


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
    return _journey_cards(_sampled_route_trips(), target_date, result_limit)


def _matching_scheduled_journeys(
    query: str,
    service_date: date,
    limit: int,
) -> list[ScheduledJourney]:
    result_limit = max(1, min(limit, 50))
    return _journey_cards(_matching_route_trips(query, result_limit), service_date, result_limit)


def _journey_cards(
    trips: list[GtfsTrip],
    target_date: date,
    result_limit: int,
) -> list[ScheduledJourney]:
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

    candidates: list[ScheduledJourney] = []
    seen_directions: set[tuple[str, str, str, str]] = set()
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
        direction_key = (
            trip.feed_version.feed.slug,
            route.route_id,
            first_stop.stop_id,
            last_stop.stop_id,
        )
        if direction_key in seen_directions:
            continue
        seen_directions.add(direction_key)
        candidates.append(
            ScheduledJourney(
                feed=trip.feed_version.feed.slug,
                trip_id=trip.trip_id,
                route_id=trip.route_id,
                mode=route_mode(route.route_type, trip.feed_version.feed.slug),
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
    return _select_diverse_journeys(candidates, result_limit)


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


def _sampled_route_trips() -> list[GtfsTrip]:
    versions = sorted(
        active_versions().select_related("feed"),
        key=lambda version: (KL_FIRST_FEED_ORDER.get(version.feed.slug, 10), version.feed.slug),
    )
    sampled: list[GtfsTrip] = []
    for version in versions:
        sampled.extend(
            GtfsTrip.objects.filter(feed_version=version)
            .select_related("feed_version__feed")
            .order_by("route_id", "trip_id")
            .distinct("route_id")[:ROUTE_SAMPLE_LIMIT],
        )
    return sampled


def _matching_route_trips(query: str, result_limit: int) -> list[GtfsTrip]:
    normalized_query = query.strip()
    matching: list[GtfsTrip] = []
    versions = sorted(
        active_versions().select_related("feed"),
        key=lambda version: (KL_FIRST_FEED_ORDER.get(version.feed.slug, 10), version.feed.slug),
    )
    for version in versions:
        route_ids = list(
            GtfsRoute.objects.filter(feed_version=version)
            .filter(
                Q(short_name__icontains=normalized_query)
                | Q(long_name__icontains=normalized_query),
            )
            .values_list("route_id", flat=True),
        )
        stop_ids = list(
            GtfsStop.objects.filter(feed_version=version)
            .filter(name__icontains=normalized_query)
            .values_list("stop_id", flat=True),
        )
        stop_trip_ids = GtfsStopTime.objects.filter(
            trip__feed_version=version,
            stop_id__in=stop_ids,
        ).values_list("trip_id", flat=True)
        trip_filter = (
            Q(trip_id__icontains=normalized_query)
            | Q(headsign__icontains=normalized_query)
            | Q(route_id__in=route_ids)
            | Q(id__in=stop_trip_ids)
        )
        folded_query = normalized_query.casefold()
        feed_matches_query = (
            folded_query in version.feed.slug.casefold()
            or folded_query in version.feed.display_name.casefold()
        )
        trips = GtfsTrip.objects.filter(feed_version=version).select_related("feed_version__feed")
        if not feed_matches_query:
            trips = trips.filter(trip_filter)
        matching.extend(trips.order_by("route_id", "trip_id")[:result_limit])
    return matching


def _select_diverse_journeys(
    candidates: list[ScheduledJourney], result_limit: int
) -> list[ScheduledJourney]:
    selected: list[ScheduledJourney] = []
    selected_ids: set[tuple[str, str]] = set()
    for mode in PRIORITY_MODES:
        journey = next((item for item in candidates if item.mode == mode), None)
        if journey is not None:
            selected.append(journey)
            selected_ids.add((journey.feed, journey.trip_id))
    for journey in candidates:
        if len(selected) == result_limit:
            break
        journey_id = (journey.feed, journey.trip_id)
        if journey_id not in selected_ids:
            selected.append(journey)
            selected_ids.add(journey_id)
    return selected[:result_limit]


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
