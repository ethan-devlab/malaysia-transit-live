import json
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from transit.http.status_api import VEHICLE_SNAPSHOT_PER_FEED_LIMIT
from transit.http.stream import vehicle_snapshot_stream
from transit.models import TransitFeed, VehicleSnapshot


@pytest.mark.django_db
def test_vehicle_snapshot_stream_matches_the_vehicle_api_contract() -> None:
    feed = TransitFeed.objects.create(
        display_name="Test stream feed",
        slug="test-stream",
        static_source_url="https://api.data.gov.my/gtfs-static/test",
    )
    now = timezone.now()
    VehicleSnapshot.objects.create(
        feed=feed,
        vehicle_id="vehicle-1",
        trip_id="trip-1",
        route_id="route-1",
        latitude="3.139",
        longitude="101.6869",
        bearing="120.5",
        speed_metres_per_second="12.25",
        position_reported_at=now,
        fetched_at=now,
        validation_state=VehicleSnapshot.ValidationState.VALIDATED,
    )

    response = vehicle_snapshot_stream(RequestFactory().get("/stream/v1/vehicles"))
    event = b"".join(response.streaming_content).decode()
    payload = json.loads(next(line[6:] for line in event.splitlines() if line.startswith("data: ")))
    vehicle = payload["vehicles"][0]

    assert set(vehicle) == {
        "feed",
        "vehicle_id",
        "trip_id",
        "route_id",
        "latitude",
        "longitude",
        "bearing",
        "speed_metres_per_second",
        "position_reported_at",
        "fetched_at",
        "freshness",
        "static_version_id",
    }
    assert vehicle["feed"] == "test-stream"
    assert vehicle["bearing"] == 120.5
    assert vehicle["speed_metres_per_second"] == 12.25
    assert vehicle["freshness"] == "live"
    assert vehicle["static_version_id"] is None


@pytest.mark.django_db
def test_vehicle_snapshot_stream_limits_positions_per_feed() -> None:
    feed = TransitFeed.objects.create(
        display_name="Bounded stream feed",
        slug="bounded-stream",
        static_source_url="https://api.data.gov.my/gtfs-static/bounded",
    )
    now = timezone.now()
    VehicleSnapshot.objects.bulk_create(
        [
            VehicleSnapshot(
                feed=feed,
                vehicle_id=f"vehicle-{index}",
                latitude="3.139",
                longitude="101.6869",
                fetched_at=now - timedelta(seconds=index),
                validation_state=VehicleSnapshot.ValidationState.VALIDATED,
            )
            for index in range(VEHICLE_SNAPSHOT_PER_FEED_LIMIT + 1)
        ],
    )

    response = vehicle_snapshot_stream(RequestFactory().get("/stream/v1/vehicles"))
    event = b"".join(response.streaming_content).decode()
    payload = json.loads(next(line[6:] for line in event.splitlines() if line.startswith("data: ")))

    assert len(payload["vehicles"]) == VEHICLE_SNAPSHOT_PER_FEED_LIMIT
    assert payload["vehicles"][0]["vehicle_id"] == "vehicle-0"
    assert payload["vehicles"][-1]["vehicle_id"] == f"vehicle-{VEHICLE_SNAPSHOT_PER_FEED_LIMIT - 1}"


@pytest.mark.django_db
def test_vehicle_snapshot_stream_preserves_coverage_across_feeds() -> None:
    first_feed = TransitFeed.objects.create(
        display_name="First coverage feed",
        slug="coverage-first",
        static_source_url="https://api.data.gov.my/gtfs-static/coverage-first",
    )
    second_feed = TransitFeed.objects.create(
        display_name="Second coverage feed",
        slug="coverage-second",
        static_source_url="https://api.data.gov.my/gtfs-static/coverage-second",
    )
    now = timezone.now()
    VehicleSnapshot.objects.bulk_create(
        [
            VehicleSnapshot(
                feed=feed,
                vehicle_id=f"{feed.slug}-{index}",
                latitude="3.139",
                longitude="101.6869",
                fetched_at=now - timedelta(seconds=index),
                validation_state=VehicleSnapshot.ValidationState.VALIDATED,
            )
            for feed in (first_feed, second_feed)
            for index in range(VEHICLE_SNAPSHOT_PER_FEED_LIMIT + 1)
        ],
    )

    response = vehicle_snapshot_stream(RequestFactory().get("/stream/v1/vehicles"))
    event = b"".join(response.streaming_content).decode()
    payload = json.loads(next(line[6:] for line in event.splitlines() if line.startswith("data: ")))
    returned_by_feed = {vehicle["feed"] for vehicle in payload["vehicles"]}

    assert returned_by_feed == {"coverage-first", "coverage-second"}
    assert len(payload["vehicles"]) == 2 * VEHICLE_SNAPSHOT_PER_FEED_LIMIT
