import pytest
from django.test import RequestFactory
from django.utils import timezone

from transit.http.status_api import data_status
from transit.models import StaticFeedVersion, TransitFeed, UpstreamFetchAttempt


@pytest.mark.django_db
def test_data_status_distinguishes_scheduled_only_and_first_realtime_fetch() -> None:
    scheduled_only_feed = TransitFeed.objects.create(
        display_name="Scheduled-only feed",
        slug="scheduled-only",
        static_source_url="https://api.data.gov.my/gtfs-static/scheduled-only",
    )
    awaiting_feed = TransitFeed.objects.create(
        display_name="Awaiting feed",
        is_realtime_enabled=True,
        realtime_source_url="https://api.data.gov.my/gtfs-realtime/vehicle-position/awaiting",
        slug="awaiting-feed",
        static_source_url="https://api.data.gov.my/gtfs-static/awaiting",
    )
    available_feed = TransitFeed.objects.create(
        display_name="Available feed",
        is_realtime_enabled=True,
        realtime_source_url="https://api.data.gov.my/gtfs-realtime/vehicle-position/available",
        slug="available-feed",
        static_source_url="https://api.data.gov.my/gtfs-static/available",
    )
    for feed in (scheduled_only_feed, awaiting_feed, available_feed):
        StaticFeedVersion.objects.create(
            content_sha256="a" * 64,
            feed=feed,
            source_url=feed.static_source_url,
            status=StaticFeedVersion.Status.ACTIVE,
        )
    now = timezone.now()
    UpstreamFetchAttempt.objects.create(
        completed_at=now,
        feed=available_feed,
        kind=UpstreamFetchAttempt.Kind.REALTIME,
        started_at=now,
        succeeded=True,
    )

    request = RequestFactory().get("/api/v1/data-status")
    statuses = {status.feed: status for status in data_status(request)}

    assert statuses["scheduled-only"].realtime_state == "scheduled_only"
    assert statuses["awaiting-feed"].realtime_state == "awaiting_first_fetch"
    assert statuses["available-feed"].realtime_state == "available"
