from datetime import timedelta

import pytest
from django.utils import timezone

from transit.models import TransitFeed, UpstreamFetchAttempt
from transit.services import realtime_poll


def test_rapid_bus_penang_suffix_fallback_requires_a_trip_identifier() -> None:
    assert (
        realtime_poll.has_known_reference(
            "rapid-bus-penang",
            "",
            "",
            {"rapid-bus-penang-101"},
            set(),
        )
        is False
    )


@pytest.mark.django_db
def test_incomplete_but_decodable_realtime_protobuf_is_recorded_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed = TransitFeed.objects.create(
        display_name="Test realtime feed",
        slug="test-realtime",
        static_source_url="https://api.data.gov.my/gtfs-static/test",
        realtime_source_url="https://api.data.gov.my/gtfs-realtime/vehicle-position/test",
        is_realtime_enabled=True,
    )
    monkeypatch.setattr(realtime_poll, "wait_for_upstream_slot", lambda _scope: None)
    monkeypatch.setattr(realtime_poll, "_download_realtime_body", lambda _url: b"\x08\x01")

    result = realtime_poll.poll_realtime_feed(feed)

    assert result.status == "failed"
    assert UpstreamFetchAttempt.objects.filter(
        feed=feed,
        kind=UpstreamFetchAttempt.Kind.REALTIME,
        succeeded=False,
        completed_at__gte=timezone.now() - timedelta(minutes=1),
    ).exists()
