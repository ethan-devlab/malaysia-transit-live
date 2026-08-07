import pytest
from django.test import RequestFactory
from django.utils import timezone

from transit.http.network_api import search_network
from transit.models import (
    GtfsRoute,
    GtfsService,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
    StaticFeedVersion,
    TransitFeed,
    VehicleSnapshot,
)


@pytest.mark.django_db
def test_network_search_returns_matching_static_trip_and_validated_vehicle() -> None:
    feed = TransitFeed.objects.create(
        display_name="Ampang test operator",
        slug="ampang-test",
        static_source_url="https://api.data.gov.my/gtfs-static/ampang-test",
    )
    version = StaticFeedVersion.objects.create(
        content_sha256="a" * 64,
        feed=feed,
        source_url=feed.static_source_url,
        status=StaticFeedVersion.Status.ACTIVE,
    )
    GtfsRoute.objects.create(
        feed_version=version,
        long_name="Ampang Line",
        route_id="AG",
        route_type=1,
        short_name="AG",
    )
    first_stop = GtfsStop.objects.create(
        feed_version=version,
        latitude="3.139000",
        longitude="101.686900",
        name="Ampang",
        stop_id="AG01",
    )
    last_stop = GtfsStop.objects.create(
        feed_version=version,
        latitude="3.140000",
        longitude="101.687900",
        name="Masjid Jamek",
        stop_id="AG02",
    )
    service = GtfsService.objects.create(
        end_date=timezone.localdate(),
        feed_version=version,
        friday=True,
        monday=True,
        saturday=True,
        service_id="daily",
        start_date=timezone.localdate(),
        sunday=True,
        thursday=True,
        tuesday=True,
        wednesday=True,
    )
    trip = GtfsTrip.objects.create(
        feed_version=version,
        headsign="Masjid Jamek",
        route_id="AG",
        service_id=service.service_id,
        trip_id="AG-AMPANG",
    )
    GtfsStopTime.objects.create(
        arrival_time="08:00:00",
        departure_time="08:00:00",
        stop_id=first_stop.stop_id,
        stop_sequence=1,
        trip=trip,
    )
    GtfsStopTime.objects.create(
        arrival_time="08:20:00",
        departure_time="08:20:00",
        stop_id=last_stop.stop_id,
        stop_sequence=2,
        trip=trip,
    )
    VehicleSnapshot.objects.create(
        feed=feed,
        feed_version=version,
        fetched_at=timezone.now(),
        latitude="3.139000",
        longitude="101.686900",
        route_id="AG",
        trip_id=trip.trip_id,
        validation_state=VehicleSnapshot.ValidationState.VALIDATED,
        vehicle_id="AMPANG-1",
    )

    result = search_network(RequestFactory().get("/api/v1/search?q=ampang"), q="ampang")

    assert [journey.trip_id for journey in result.journeys] == [trip.trip_id]
    assert [route.route_id for route in result.routes] == ["AG"]
    assert [stop.stop_id for stop in result.stops] == [first_stop.stop_id]
    assert [vehicle.vehicle_id for vehicle in result.vehicles] == ["AMPANG-1"]
