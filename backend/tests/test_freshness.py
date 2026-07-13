from datetime import UTC, datetime, timedelta

from transit.domain.freshness import DataStatus, freshness_status


def test_freshness_status_when_realtime_is_recent_returns_live() -> None:
    # Given
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)

    # When
    status = freshness_status(
        realtime_available=True,
        last_successful_fetch_at=now - timedelta(seconds=30),
        now=now,
    )

    # Then
    assert status is DataStatus.LIVE


def test_freshness_status_when_realtime_is_old_returns_stale() -> None:
    # Given
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)

    # When
    status = freshness_status(
        realtime_available=True,
        last_successful_fetch_at=now - timedelta(seconds=91),
        now=now,
    )

    # Then
    assert status is DataStatus.STALE


def test_freshness_status_when_feed_has_no_realtime_returns_scheduled_only() -> None:
    # Given
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)

    # When
    status = freshness_status(
        realtime_available=False,
        last_successful_fetch_at=None,
        now=now,
    )

    # Then
    assert status is DataStatus.SCHEDULED_ONLY
