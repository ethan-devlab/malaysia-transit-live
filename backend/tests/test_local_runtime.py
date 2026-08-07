from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from transit import tasks
from transit.http.origin import WorkerOriginVerificationMiddleware
from transit.management.commands import sync_gtfs_static
from transit.models import StaticFeedVersion, TransitFeed, UpstreamFetchAttempt
from transit.services import upstream_rate_limit
from transit.services.archive_contracts import ArchiveStorageError
from transit.services.archive_store import FilesystemArchiveStore, archive_store_from_environment
from transit.services.local_bootstrap import static_refresh_is_due
from transit.services.static_import.retention import prune_local_static_versions
from transit.services.static_refresh import StaticRefreshResult, _archive_object_key

MALAYSIA_TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")


def test_filesystem_archive_store_when_given_safe_key_persists_and_removes_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    source_zip = tmp_path / "source.zip"
    source_zip.write_bytes(b"GTFS")
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("TRANSIT_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("TRANSIT_ARCHIVE_DIRECTORY", str(archive_root))
    store = archive_store_from_environment()
    object_key = "gtfs-static/test-feed/2026/07/13/source.zip"

    # When
    store.put_zip(source_zip, object_key)

    # Then
    destination = archive_root / "gtfs-static" / "test-feed" / "2026" / "07" / "13" / "source.zip"
    assert destination.read_bytes() == b"GTFS"

    # When
    store.delete_zip(object_key)

    # Then
    assert not destination.exists()


def test_filesystem_archive_store_when_given_unsafe_key_raises_typed_error(tmp_path: Path) -> None:
    # Given
    source_zip = tmp_path / "source.zip"
    source_zip.write_bytes(b"GTFS")
    store = FilesystemArchiveStore(tmp_path / "archives")

    # When / Then
    with pytest.raises(ArchiveStorageError):
        store.put_zip(source_zip, "../outside.zip")


@pytest.mark.django_db
def test_static_refresh_is_due_when_feed_has_no_active_version() -> None:
    # Given
    _create_feed()
    now = datetime(2026, 7, 13, 5, tzinfo=MALAYSIA_TIMEZONE)

    # When
    due = static_refresh_is_due(now)

    # Then
    assert due is True


@pytest.mark.django_db
def test_static_refresh_is_due_when_every_feed_refreshed_after_daily_cutoff_returns_false() -> None:
    # Given
    feed = _create_feed()
    now = datetime(2026, 7, 13, 5, tzinfo=MALAYSIA_TIMEZONE)
    _create_version(feed, StaticFeedVersion.Status.ACTIVE, "current.zip", now)
    UpstreamFetchAttempt.objects.create(
        completed_at=now - timedelta(minutes=10),
        feed=feed,
        kind=UpstreamFetchAttempt.Kind.STATIC,
        started_at=now - timedelta(minutes=11),
        succeeded=True,
    )

    # When
    due = static_refresh_is_due(now)

    # Then
    assert due is False


@pytest.mark.django_db
def test_prune_local_static_versions_when_third_version_activates_keeps_one_predecessor() -> None:
    # Given
    feed = _create_feed()
    now = datetime(2026, 7, 13, 5, tzinfo=MALAYSIA_TIMEZONE)
    oldest = _create_version(
        feed,
        StaticFeedVersion.Status.ARCHIVED,
        "oldest.zip",
        now - timedelta(days=2),
    )
    predecessor = _create_version(
        feed,
        StaticFeedVersion.Status.ARCHIVED,
        "predecessor.zip",
        now - timedelta(days=1),
    )
    active = _create_version(feed, StaticFeedVersion.Status.ACTIVE, "active.zip", now)

    # When
    archive_store = _TrackingArchiveStore()
    pruned = prune_local_static_versions(feed, archive_store)

    # Then
    assert pruned == 1
    assert archive_store.deleted_keys == ["oldest.zip"]
    assert not StaticFeedVersion.objects.filter(pk=oldest.pk).exists()
    assert StaticFeedVersion.objects.filter(pk=predecessor.pk).exists()
    assert StaticFeedVersion.objects.filter(pk=active.pk).exists()


@pytest.mark.django_db
def test_prune_local_static_versions_when_versions_share_archive_keeps_referenced_zip() -> None:
    # Given
    feed = _create_feed()
    now = datetime(2026, 7, 13, 5, tzinfo=MALAYSIA_TIMEZONE)
    oldest = _create_version(
        feed,
        StaticFeedVersion.Status.ARCHIVED,
        "shared.zip",
        now - timedelta(days=2),
    )
    _create_version(feed, StaticFeedVersion.Status.ARCHIVED, "shared.zip", now - timedelta(days=1))
    _create_version(feed, StaticFeedVersion.Status.ACTIVE, "shared.zip", now)
    archive_store = _TrackingArchiveStore()

    # When
    pruned = prune_local_static_versions(feed, archive_store)

    # Then
    assert pruned == 1
    assert archive_store.deleted_keys == []
    assert not StaticFeedVersion.objects.filter(pk=oldest.pk).exists()


@pytest.mark.django_db
def test_prune_local_static_versions_when_archive_is_locked_keeps_the_version_for_retry() -> None:
    feed = _create_feed()
    now = datetime(2026, 7, 13, 5, tzinfo=MALAYSIA_TIMEZONE)
    oldest = _create_version(
        feed,
        StaticFeedVersion.Status.ARCHIVED,
        "locked.zip",
        now - timedelta(days=2),
    )
    _create_version(
        feed,
        StaticFeedVersion.Status.ARCHIVED,
        "previous.zip",
        now - timedelta(days=1),
    )
    _create_version(feed, StaticFeedVersion.Status.ACTIVE, "active.zip", now)

    pruned = prune_local_static_versions(feed, _LockedArchiveStore())

    assert pruned == 0
    assert StaticFeedVersion.objects.filter(pk=oldest.pk).exists()


@pytest.mark.django_db
def test_prune_local_static_versions_removes_abandoned_staged_version() -> None:
    feed = _create_feed()
    now = datetime(2026, 7, 13, 5, tzinfo=MALAYSIA_TIMEZONE)
    staged = _create_version(feed, StaticFeedVersion.Status.STAGED, "staged.zip", now)
    _create_version(feed, StaticFeedVersion.Status.ACTIVE, "active.zip", now)
    archive_store = _TrackingArchiveStore()

    pruned = prune_local_static_versions(feed, archive_store)

    assert pruned == 1
    assert archive_store.deleted_keys == ["staged.zip"]
    assert not StaticFeedVersion.objects.filter(pk=staged.pk).exists()


def test_archive_object_keys_are_unique_for_identical_content() -> None:
    first = _archive_object_key("ktmb", "a" * 64)
    second = _archive_object_key("ktmb", "a" * 64)

    assert first != second
    assert first.endswith(".zip")
    assert second.endswith(".zip")


@override_settings(DEBUG=False, LOCAL_ONLY=True, WORKER_ORIGIN_SECRET="")
def test_worker_origin_middleware_when_local_only_allows_api_without_edge_secret() -> None:
    # Given
    request = RequestFactory().get("/api/v1/data-status")
    middleware = WorkerOriginVerificationMiddleware(lambda _request: HttpResponse(status=204))

    # When
    response = middleware(request)

    # Then
    assert response.status_code == 204


def test_refresh_static_gtfs_when_a_feed_fails_requests_a_bounded_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrying_task = _RetryingTask()
    monkeypatch.setattr(tasks, "archive_store_from_environment", _archive_store_from_environment)
    monkeypatch.setattr(tasks, "singleton_task_lock", _acquired_task_lock)
    monkeypatch.setattr(
        tasks,
        "StaticFeedRefresher",
        lambda _archive_store: _FailingStaticFeedRefresher(),
    )
    monkeypatch.setattr(tasks, "prune_local_audit_history", lambda _archive_store: None)
    monkeypatch.setattr(tasks.refresh_static_gtfs, "retry", retrying_task.retry)

    with pytest.raises(_RetryRequestedError):
        tasks.refresh_static_gtfs.run()

    assert retrying_task.exception.args == ("1 official static GTFS feeds failed to refresh.",)
    assert retrying_task.retry_kwargs == {"retry_feed_slugs": ["ktmb"]}


@override_settings(LOCAL_ONLY=True)
def test_manual_static_sync_when_local_prunes_audit_with_its_archive_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    archive_store = object()
    refresher_stores: list[object] = []
    pruned_stores: list[object] = []

    def create_refresher(store: object) -> _FailingStaticFeedRefresher:
        refresher_stores.append(store)
        return _FailingStaticFeedRefresher()

    monkeypatch.setattr(sync_gtfs_static, "archive_store_from_environment", lambda: archive_store)
    monkeypatch.setattr(sync_gtfs_static, "StaticFeedRefresher", create_refresher)
    monkeypatch.setattr(
        sync_gtfs_static,
        "prune_local_audit_history",
        pruned_stores.append,
    )

    # When
    sync_gtfs_static.Command().handle(feed=None)

    # Then
    assert refresher_stores == [archive_store]
    assert pruned_stores == [archive_store]


@override_settings(LOCAL_ONLY=True)
def test_refresh_static_gtfs_when_local_refresh_is_current_skips_duplicate_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "singleton_task_lock", _acquired_task_lock)
    monkeypatch.setattr(tasks, "static_refresh_is_due", lambda _now: False)
    monkeypatch.setattr(tasks, "archive_store_from_environment", _unexpected_archive_store)

    result = tasks.refresh_static_gtfs.run()

    assert result == {"active": 0, "failed": 0, "skipped": 1}


def test_wait_for_upstream_slot_reserves_one_key_per_official_api_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _AvailableSlotClient()
    monkeypatch.setattr(upstream_rate_limit.Redis, "from_url", lambda *_args, **_kwargs: client)

    upstream_rate_limit.wait_for_upstream_slot("gtfs-static")
    upstream_rate_limit.wait_for_upstream_slot("gtfs-realtime")

    assert client.set_calls == [
        (
            "malaysia-transit-live:upstream-slot:gtfs-static",
            True,
            upstream_rate_limit.REQUEST_INTERVAL_SECONDS,
        ),
        (
            "malaysia-transit-live:upstream-slot:gtfs-realtime",
            True,
            upstream_rate_limit.REQUEST_INTERVAL_SECONDS,
        ),
    ]


def test_realtime_task_uses_lock_longer_than_the_maximum_four_feed_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_timeouts: list[int] = []

    @contextmanager
    def capture_lock(_name: str, timeout_seconds: int) -> Iterator[bool]:
        observed_timeouts.append(timeout_seconds)
        yield True

    monkeypatch.setattr(tasks, "singleton_task_lock", capture_lock)
    monkeypatch.setattr(tasks, "poll_realtime_cycle", list)

    result = tasks.poll_realtime_vehicle_positions.run()

    assert result == {
        "accepted_positions": 0,
        "deferred_feeds": 0,
        "failed_feeds": 0,
        "polled_feeds": 0,
        "skipped": 0,
    }
    assert observed_timeouts == [tasks.REALTIME_POLL_LOCK_TIMEOUT_SECONDS]
    assert tasks.REALTIME_POLL_LOCK_TIMEOUT_SECONDS > 4 * 20


def _create_feed() -> TransitFeed:
    return TransitFeed.objects.create(
        display_name="Test feed",
        slug="test-feed",
        static_source_url="https://example.com/static.zip",
    )


def _create_version(
    feed: TransitFeed,
    status: str,
    archive_object_key: str,
    activated_at: datetime,
) -> StaticFeedVersion:
    return StaticFeedVersion.objects.create(
        activated_at=activated_at,
        archive_object_key=archive_object_key,
        content_sha256="a" * 64,
        feed=feed,
        source_url=feed.static_source_url,
        status=status,
    )


class _RetryRequestedError(Exception):
    pass


class _RetryingTask:
    def __init__(self) -> None:
        self.exception: Exception | None = None
        self.retry_kwargs: dict[str, list[str]] | None = None

    def retry(self, *, exc: Exception, kwargs: dict[str, list[str]]) -> None:
        self.exception = exc
        self.retry_kwargs = kwargs
        raise _RetryRequestedError


class _FailingStaticFeedRefresher:
    def refresh_all(self, _feed_slug: str | None = None) -> list[StaticRefreshResult]:
        return [StaticRefreshResult(feed_slug="ktmb", status="failed")]


@contextmanager
def _acquired_task_lock(*_args: object, **_kwargs: object) -> Iterator[bool]:
    yield True


def _archive_store_from_environment() -> object:
    return object()


def _unexpected_archive_store() -> object:
    raise AssertionError("A current local refresh must not fetch a duplicate static dataset.")


class _AvailableSlotClient:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, bool, int]] = []

    def set(self, key: str, _token: str, *, nx: bool, ex: int) -> bool:
        self.set_calls.append((key, nx, ex))
        return True


class _TrackingArchiveStore:
    def __init__(self) -> None:
        self.deleted_keys: list[str] = []

    def delete_zip(self, object_key: str) -> None:
        self.deleted_keys.append(object_key)


class _LockedArchiveStore:
    def delete_zip(self, _object_key: str) -> None:
        raise ArchiveStorageError("archive is locked")
