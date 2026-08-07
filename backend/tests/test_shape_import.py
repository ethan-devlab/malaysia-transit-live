from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from transit.models import (
    GtfsShapePoint,
    StaticFeedVersion,
    StaticImportIssue,
    TransitFeed,
)
from transit.services.static_import import shape_loader
from transit.services.static_import.contracts import StaticImportError
from transit.services.static_import.orchestrator import import_static_gtfs_archive


@pytest.mark.django_db
def test_valid_shapes_import_ordered_points_and_coverage(tmp_path: Path) -> None:
    archive_path = _write_archive(
        tmp_path,
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled
shape-a,3.100000,101.600000,0,0
shape-a,3.200000,101.700000,1,1.25
shape-b,3.300000,101.800000,0,
""",
    )
    feed = _create_feed("valid-shapes")

    result = import_static_gtfs_archive(feed, archive_path)

    version = StaticFeedVersion.objects.get(pk=result.version_id)
    points = list(
        GtfsShapePoint.objects.filter(feed_version=version).order_by("shape_id", "sequence")
    )
    assert result.status == StaticFeedVersion.Status.ACTIVE
    assert result.record_counts["shapes"] == 2
    assert result.record_counts["shape_points"] == 3
    assert result.record_counts["trips_with_shape"] == 1
    assert result.record_counts["trips_without_shape"] == 0
    assert result.record_counts["orphan_trip_shapes"] == 0
    assert [(point.shape_id, point.sequence) for point in points] == [
        ("shape-a", 0),
        ("shape-a", 1),
        ("shape-b", 0),
    ]
    assert str(points[1].distance_travelled) == "1.250000"
    assert points[2].distance_travelled is None
    assert version.status == StaticFeedVersion.Status.ACTIVE


@pytest.mark.django_db
def test_missing_shapes_file_activates_with_zero_shape_counts(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, shapes=None, trip_shape_id="")
    feed = _create_feed("missing-shapes")

    result = import_static_gtfs_archive(feed, archive_path)

    version = StaticFeedVersion.objects.get(pk=result.version_id)
    assert version.status == StaticFeedVersion.Status.ACTIVE
    assert result.record_counts["shapes"] == 0
    assert result.record_counts["shape_points"] == 0
    assert result.record_counts["trips_with_shape"] == 0
    assert result.record_counts["trips_without_shape"] == 1
    assert result.record_counts["orphan_trip_shapes"] == 0
    assert not version.import_issues.filter(code="orphan_trip_shape_reference").exists()


@pytest.mark.django_db
def test_duplicate_shape_sequence_rejects_staged_version_and_preserves_active(
    tmp_path: Path,
) -> None:
    feed = _create_feed("duplicate-shapes")
    active_archive = _write_archive(
        tmp_path / "active",
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shape-a,3.1,101.6,0
shape-a,3.2,101.7,1
""",
    )
    active_result = import_static_gtfs_archive(feed, active_archive)
    duplicate_archive = _write_archive(
        tmp_path / "duplicate",
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shape-a,3.1,101.6,0
shape-a,3.2,101.7,0
""",
    )

    with pytest.raises(StaticImportError) as raised:
        import_static_gtfs_archive(feed, duplicate_archive)

    active_version = StaticFeedVersion.objects.get(pk=active_result.version_id)
    rejected_version = StaticFeedVersion.objects.exclude(pk=active_version.pk).get(feed=feed)
    assert raised.value.code == "duplicate_identifier"
    assert raised.value.source_file == "shapes.txt"
    assert raised.value.row_number == 3
    assert active_version.status == StaticFeedVersion.Status.ACTIVE
    assert rejected_version.status == StaticFeedVersion.Status.REJECTED
    issue = rejected_version.import_issues.get(severity=StaticImportIssue.Severity.ERROR)
    assert issue.source_file == "shapes.txt"


@pytest.mark.django_db
def test_shape_coordinate_bounds_reject_with_source_row(tmp_path: Path) -> None:
    archive_path = _write_archive(
        tmp_path,
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shape-a,90.000001,101.6,0
""",
    )
    feed = _create_feed("invalid-coordinate")

    with pytest.raises(StaticImportError) as raised:
        import_static_gtfs_archive(feed, archive_path)

    assert raised.value.code == "invalid_coordinate"
    assert raised.value.source_file == "shapes.txt"
    assert raised.value.row_number == 2
    assert StaticFeedVersion.objects.get(feed=feed).status == StaticFeedVersion.Status.REJECTED


@pytest.mark.django_db
def test_shape_distance_must_be_non_decreasing(tmp_path: Path) -> None:
    archive_path = _write_archive(
        tmp_path,
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled
shape-a,3.1,101.6,0,2
shape-a,3.2,101.7,1,1
""",
    )
    feed = _create_feed("non-monotonic-distance")

    with pytest.raises(StaticImportError) as raised:
        import_static_gtfs_archive(feed, archive_path)

    assert raised.value.code == "invalid_distance"
    assert raised.value.source_file == "shapes.txt"
    assert raised.value.row_number == 3


@pytest.mark.django_db
def test_shape_distance_validation_uses_point_sequence_not_archive_order(tmp_path: Path) -> None:
    archive_path = _write_archive(
        tmp_path,
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled
shape-a,3.2,101.7,1,2
shape-a,3.1,101.6,0,1
""",
    )
    feed = _create_feed("unordered-shape-rows")

    result = import_static_gtfs_archive(feed, archive_path)

    assert result.status == StaticFeedVersion.Status.ACTIVE
    assert result.record_counts["shape_points"] == 2


@pytest.mark.django_db
def test_orphan_trip_shape_reference_warns_without_rejecting(tmp_path: Path) -> None:
    archive_path = _write_archive(
        tmp_path,
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shape-present,3.1,101.6,0
shape-present,3.2,101.7,1
""",
        trip_shape_id="shape-missing",
    )
    feed = _create_feed("orphan-shape")

    result = import_static_gtfs_archive(feed, archive_path)

    version = StaticFeedVersion.objects.get(pk=result.version_id)
    warnings = version.import_issues.filter(
        severity=StaticImportIssue.Severity.WARNING,
        code="orphan_trip_shape_reference",
    )
    assert result.record_counts["trips_with_shape"] == 1
    assert result.record_counts["trips_without_shape"] == 0
    assert result.record_counts["orphan_trip_shapes"] == 1
    assert warnings.count() == 1
    warning = warnings.get()
    assert warning.source_file == "trips.txt"
    assert "1" in warning.detail
    assert "missing from shapes.txt" in warning.detail
    assert version.status == StaticFeedVersion.Status.ACTIVE


@pytest.mark.django_db
def test_shape_point_limit_rejects_at_loader_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shape_loader, "MAX_POINTS_PER_SHAPE", 1)
    archive_path = _write_archive(
        tmp_path,
        shapes="""shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shape-a,3.1,101.6,0
shape-a,3.2,101.7,1
""",
    )
    feed = _create_feed("shape-limit")

    with pytest.raises(StaticImportError) as raised:
        import_static_gtfs_archive(feed, archive_path)

    assert raised.value.code == "shape_too_large"
    assert raised.value.source_file == "shapes.txt"
    assert raised.value.row_number == 3
    version = StaticFeedVersion.objects.get(feed=feed)
    assert version.status == StaticFeedVersion.Status.REJECTED
    assert not GtfsShapePoint.objects.filter(feed_version=version).exists()


def _create_feed(slug: str) -> TransitFeed:
    return TransitFeed.objects.create(
        display_name=slug,
        slug=slug,
        static_source_url=f"https://example.com/{slug}.zip",
    )


def _write_archive(
    directory: Path,
    *,
    shapes: str | None,
    trip_shape_id: str = "shape-a",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    archive_path = directory / "feed.zip"
    files = {
        "agency.txt": "agency_name,agency_url,agency_timezone\nTransit,https://example.com,Asia/Kuala_Lumpur\n",
        "routes.txt": "route_id,route_type\nR1,3\n",
        "stops.txt": (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "S1,One,3.100000,101.600000\n"
            "S2,Two,3.200000,101.700000\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "daily,1,1,1,1,1,1,1,20260101,20261231\n"
        ),
        "trips.txt": f"route_id,service_id,trip_id,shape_id\nR1,daily,T1,{trip_shape_id}\n",
        "stop_times.txt": (
            "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
            "T1,S1,0,08:00:00,08:00:00\n"
            "T1,S2,1,08:10:00,08:10:00\n"
        ),
    }
    if shapes is not None:
        files["shapes.txt"] = shapes
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return archive_path
