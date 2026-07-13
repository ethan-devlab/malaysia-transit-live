"""Transactional orchestration for immutable GTFS static version imports."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone

from transit.models import StaticFeedVersion, StaticImportIssue, TransitFeed
from transit.services.static_import.archive import has_member, inspect_archive
from transit.services.static_import.contracts import StaticImportError, StaticImportResult
from transit.services.static_import.core_loaders import load_agencies, load_routes, load_stops
from transit.services.static_import.schedule_loaders import (
    load_services,
    load_stop_times,
    load_trips,
)

REQUIRED_RECORD_FILES = {
    "agencies": "agency.txt",
    "routes": "routes.txt",
    "stops": "stops.txt",
    "trips": "trips.txt",
    "stop_times": "stop_times.txt",
}


def import_static_gtfs_archive(
    feed: TransitFeed,
    archive_path: Path,
    archive_object_key: str = "",
) -> StaticImportResult:
    """Stage, validate, load, and atomically activate one full GTFS static ZIP."""
    inspection = inspect_archive(archive_path)
    version = StaticFeedVersion.objects.create(
        feed=feed,
        source_url=feed.static_source_url,
        content_sha256=inspection.content_sha256,
        archive_object_key=archive_object_key,
        manifest=inspection.manifest,
    )
    try:
        with zipfile.ZipFile(archive_path) as archive, transaction.atomic():
            record_counts = _load_all_records(archive, version)
            warnings = _build_warnings(archive)
            _activate_version(version, record_counts, warnings)
    except StaticImportError as error:
        _reject_version(version, error)
        raise
    except (IntegrityError, ValueError) as error:
        internal_error = StaticImportError(
            "persistence_failure",
            "The dataset could not be persisted after validation.",
            "database",
        )
        _reject_version(version, internal_error)
        raise internal_error from error

    return StaticImportResult(
        version_id=str(version.id),
        status=StaticFeedVersion.Status.ACTIVE,
        record_counts=record_counts,
        archive_path=archive_path,
    )


def _load_all_records(
    archive: zipfile.ZipFile,
    version: StaticFeedVersion,
) -> dict[str, int]:
    service_count, exception_count = load_services(archive, version)
    record_counts = {
        "agencies": load_agencies(archive, version),
        "routes": load_routes(archive, version),
        "stops": load_stops(archive, version),
        "services": service_count,
        "service_exceptions": exception_count,
        "trips": load_trips(archive, version),
        "stop_times": load_stop_times(archive, version),
    }
    for record_name, source_file in REQUIRED_RECORD_FILES.items():
        if record_counts[record_name] == 0:
            raise StaticImportError(
                "empty_required_file",
                f"{source_file} contains no usable records.",
                source_file,
            )
    return record_counts


def _build_warnings(archive: zipfile.ZipFile) -> tuple[tuple[str, str, str], ...]:
    warnings: list[tuple[str, str, str]] = []
    if not has_member(archive, "calendar.txt"):
        warnings.append(
            (
                "calendar_dates_only",
                "calendar_dates.txt",
                "Calendar service is defined solely by exception dates.",
            )
        )
    if not has_member(archive, "feed_info.txt"):
        warnings.append(
            (
                "feed_info_missing",
                "feed_info.txt",
                "feed_info.txt is absent; source version metadata is unavailable.",
            )
        )
    return tuple(warnings)


def _activate_version(
    version: StaticFeedVersion,
    record_counts: dict[str, int],
    warnings: Sequence[tuple[str, str, str]],
) -> None:
    now = timezone.now()
    StaticFeedVersion.objects.filter(
        feed=version.feed,
        status=StaticFeedVersion.Status.ACTIVE,
    ).exclude(pk=version.pk).update(status=StaticFeedVersion.Status.ARCHIVED)
    version.status = StaticFeedVersion.Status.ACTIVE
    version.record_counts = record_counts
    version.warnings_count = len(warnings)
    version.validated_at = now
    version.activated_at = now
    version.save(
        update_fields=(
            "status",
            "record_counts",
            "warnings_count",
            "validated_at",
            "activated_at",
        )
    )
    StaticImportIssue.objects.bulk_create(
        [
            StaticImportIssue(
                version=version,
                severity=StaticImportIssue.Severity.WARNING,
                code=code,
                source_file=source_file,
                detail=detail,
            )
            for code, source_file, detail in warnings
        ]
    )


def _reject_version(version: StaticFeedVersion, error: StaticImportError) -> None:
    version.status = StaticFeedVersion.Status.REJECTED
    version.failure_reason = error.detail
    version.save(update_fields=("status", "failure_reason"))
    StaticImportIssue.objects.create(
        version=version,
        severity=StaticImportIssue.Severity.ERROR,
        code=error.code,
        source_file=error.source_file,
        row_number=error.row_number,
        detail=error.detail,
    )
