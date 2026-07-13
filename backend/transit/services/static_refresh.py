"""Serial, rate-limited daily refresh of every official static GTFS feed."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx2
from django.utils import timezone

from transit.models import TransitFeed, UpstreamFetchAttempt
from transit.services.feed_registry import ensure_official_feed_registry
from transit.services.r2_archive import ArchiveUploadError, R2ArchiveStore
from transit.services.static_import import import_static_gtfs_archive
from transit.services.static_import.archive import MAX_ARCHIVE_BYTES, inspect_archive
from transit.services.static_import.contracts import StaticImportError
from transit.services.upstream_rate_limit import UpstreamRateLimitError, wait_for_upstream_slot

GTFS_ACCEPT_HEADER = "application/zip, application/octet-stream, */*"
HTTP_OK = 200


class StaticFetchError(RuntimeError):
    """A safe, user-independent failure while downloading a static GTFS archive."""

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class StaticRefreshResult:
    """One feed outcome suitable for structured task logging."""

    feed_slug: str
    status: str
    version_id: str | None = None
    detail: str = ""


class StaticFeedRefresher:
    """Refresh official feeds serially so one worker never exceeds 4 requests/minute."""

    def __init__(self, archive_store: R2ArchiveStore) -> None:
        self._archive_store = archive_store

    def refresh_all(self, only_feed_slug: str | None = None) -> list[StaticRefreshResult]:
        """Upsert the registry and fetch every requested feed one after another."""
        feeds = ensure_official_feed_registry()
        selected_feeds = [feed for feed in feeds if feed.slug == only_feed_slug]
        if only_feed_slug and not selected_feeds:
            raise ValueError(f"Unknown official feed: {only_feed_slug}")
        if not only_feed_slug:
            selected_feeds = feeds
        return [self.refresh_feed(feed) for feed in selected_feeds]

    def refresh_feed(self, feed: TransitFeed) -> StaticRefreshResult:
        """Fetch, archive, validate, and activate one static snapshot."""
        started_at = timezone.now()
        started_monotonic = time.monotonic()
        status_code: int | None = None
        try:
            with tempfile.TemporaryDirectory(prefix=f"gtfs-{feed.slug}-") as directory:
                archive_path = Path(directory) / "source.zip"
                status_code = self._download_archive(feed.static_source_url, archive_path)
                inspection = inspect_archive(archive_path)
                object_key = _archive_object_key(feed.slug, inspection.content_sha256)
                self._archive_store.put_zip(archive_path, object_key)
                result = import_static_gtfs_archive(feed, archive_path, object_key)
        except (StaticFetchError, StaticImportError) as error:
            self._record_fetch(
                feed,
                started_at,
                started_monotonic,
                succeeded=False,
                status_code=status_code or getattr(error, "status_code", None),
                detail=getattr(error, "detail", "Static refresh failed."),
            )
            return StaticRefreshResult(feed.slug, "failed", detail="Static refresh failed.")
        except (ArchiveUploadError, OSError):
            self._record_fetch(
                feed,
                started_at,
                started_monotonic,
                succeeded=False,
                status_code=status_code,
                detail="Static refresh failed during archive persistence.",
            )
            return StaticRefreshResult(feed.slug, "failed", detail="Static refresh failed.")

        self._record_fetch(
            feed,
            started_at,
            started_monotonic,
            succeeded=True,
            status_code=status_code,
            content_sha256=inspection.content_sha256,
        )
        return StaticRefreshResult(feed.slug, "active", version_id=result.version_id)

    def _download_archive(self, source_url: str, destination: Path) -> int:
        try:
            wait_for_upstream_slot("gtfs-static")
        except UpstreamRateLimitError as error:
            raise StaticFetchError("The shared static request gate is unavailable.") from error
        bytes_written = 0
        try:
            with httpx2.stream(
                "GET",
                source_url,
                follow_redirects=True,
                headers={"Accept": GTFS_ACCEPT_HEADER},
                timeout=60.0,
            ) as response:
                if response.status_code != HTTP_OK:
                    raise StaticFetchError(
                        "Official static source returned an unsuccessful response.",
                        response.status_code,
                    )
                with destination.open("wb") as archive_file:
                    for chunk in response.iter_bytes():
                        bytes_written += len(chunk)
                        if bytes_written > MAX_ARCHIVE_BYTES:
                            raise StaticFetchError(
                                "Official static source exceeded the archive limit.",
                            )
                        archive_file.write(chunk)
        except httpx2.HTTPError as error:
            raise StaticFetchError("Official static source could not be reached.") from error
        if bytes_written == 0:
            raise StaticFetchError("Official static source returned an empty archive.")
        return 200

    @staticmethod
    def _record_fetch(
        feed: TransitFeed,
        started_at: datetime,
        started_monotonic: float,
        *,
        succeeded: bool,
        status_code: int | None,
        content_sha256: str = "",
        detail: str = "",
    ) -> None:
        completed_at = timezone.now()
        duration_ms = max(0, round((time.monotonic() - started_monotonic) * 1_000))
        UpstreamFetchAttempt.objects.create(
            feed=feed,
            kind=UpstreamFetchAttempt.Kind.STATIC,
            succeeded=succeeded,
            status_code=status_code,
            duration_ms=duration_ms,
            content_sha256=content_sha256,
            detail=detail[:240],
            started_at=started_at,
            completed_at=completed_at,
        )


def _archive_object_key(feed_slug: str, content_sha256: str) -> str:
    date_path = timezone.localdate().strftime("%Y/%m/%d")
    return f"gtfs-static/{feed_slug}/{date_path}/{content_sha256}.zip"
