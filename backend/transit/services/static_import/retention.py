"""Bound local-only retention for historic GTFS imports and audit rows."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from django.utils import timezone

from transit.models import StaticFeedVersion, TransitFeed, UpstreamFetchAttempt
from transit.services.archive_store import ArchiveStorageError, ArchiveStore

AUDIT_RETENTION_DAYS: Final = 7
RETAINED_SUCCESSFUL_VERSIONS: Final = 2


def prune_local_static_versions(feed: TransitFeed, archive_store: ArchiveStore) -> int:
    """Keep the active version and predecessor, retrying archive cleanup before deletion."""
    retained_archived_count = RETAINED_SUCCESSFUL_VERSIONS - 1
    archived_versions = list(
        StaticFeedVersion.objects.filter(
            feed=feed,
            status=StaticFeedVersion.Status.ARCHIVED,
        ).order_by("-activated_at", "-started_at")[retained_archived_count:]
    )
    abandoned_staged_versions = list(
        StaticFeedVersion.objects.filter(
            feed=feed,
            status=StaticFeedVersion.Status.STAGED,
        )
    )
    return _prune_versions((*archived_versions, *abandoned_staged_versions), archive_store)


def prune_local_audit_history(archive_store: ArchiveStore) -> int:
    """Bound local audit metadata, retaining rows when archive deletion needs retrying."""
    cutoff = timezone.now() - timedelta(days=AUDIT_RETENTION_DAYS)
    rejected_versions = list(
        StaticFeedVersion.objects.filter(
            status=StaticFeedVersion.Status.REJECTED,
            started_at__lt=cutoff,
        )
    )
    pruned = _prune_versions(rejected_versions, archive_store)
    UpstreamFetchAttempt.objects.filter(completed_at__lt=cutoff).delete()
    return pruned


def _prune_versions(
    versions: tuple[StaticFeedVersion, ...] | list[StaticFeedVersion],
    archive_store: ArchiveStore,
) -> int:
    """Remove a version only after its unshared archive is deleted or confirmed shared."""
    pruned = 0
    for version in versions:
        archive_key = version.archive_object_key
        has_other_reference = archive_key and StaticFeedVersion.objects.filter(
            archive_object_key=archive_key,
        ).exclude(pk=version.pk).exists()
        if archive_key and not has_other_reference:
            try:
                archive_store.delete_zip(archive_key)
            except ArchiveStorageError:
                continue
        version.delete()
        pruned += 1
    return pruned
