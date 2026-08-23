from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from transit.models import (
    GtfsRoute,
    GtfsService,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
    StaticFeedVersion,
    TransitFeed,
)
from transit.services.rail_alignment import derive_alignments, write_review_report
from transit.services.rail_infrastructure import (
    OSM_ATTRIBUTION,
    import_overpass_snapshot,
    import_rail_snapshot,
    invalidate_snapshot,
    latest_accepted_alignment,
)


@pytest.mark.django_db
def test_given_a_local_osm_snapshot_when_importing_then_persists_an_immutable_rail_graph(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "ktmb-rail.json"
    archive_path.write_text(json.dumps(_snapshot_payload()), encoding="utf-8")

    snapshot, created = import_overpass_snapshot(
        archive_path,
        source_captured_at=None,
        source_url="https://overpass-api.de/api/interpreter",
    )
    repeated_snapshot, repeated_created = import_overpass_snapshot(
        archive_path,
        source_captured_at=None,
        source_url="https://overpass-api.de/api/interpreter",
    )

    assert created
    assert snapshot.attribution == OSM_ATTRIBUTION
    assert snapshot.content_sha256
    assert snapshot.geographic_extent == {
        "max_latitude": 3.0,
        "max_longitude": 101.008,
        "min_latitude": 3.0,
        "min_longitude": 101.0,
    }
    assert snapshot.nodes.count() == 3
    assert snapshot.edges.count() == 2
    assert repeated_snapshot.id == snapshot.id
    assert not repeated_created


@pytest.mark.django_db
def test_given_filtered_osm_xml_when_importing_then_uses_the_same_normalized_graph(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "ktmb-rail.osm"
    archive_path.write_text(_xml_snapshot(), encoding="utf-8")

    snapshot, created = import_rail_snapshot(
        archive_path,
        source_captured_at=datetime(2026, 8, 1, 22, 57, 54, tzinfo=UTC),
        source_url="https://download.geofabrik.de/asia/malaysia-singapore-brunei-260801.osm.pbf",
    )

    assert created
    assert snapshot.source_captured_at.isoformat() == "2026-08-01T22:57:54+00:00"
    assert snapshot.nodes.count() == 3
    assert snapshot.edges.count() == 2


@pytest.mark.django_db
def test_given_versioned_inputs_when_deriving_then_reuses_the_same_result_and_invalidates_safely(
    tmp_path: Path,
) -> None:
    version, trip = _scheduled_trip()
    archive_path = tmp_path / "ktmb-rail.json"
    archive_path.write_text(json.dumps(_snapshot_payload()), encoding="utf-8")
    snapshot, _ = import_overpass_snapshot(
        archive_path,
        source_captured_at=None,
        source_url="https://overpass-api.de/api/interpreter",
    )

    first = derive_alignments(version, snapshot)
    second = derive_alignments(version, snapshot)
    report_path = tmp_path / "review.json"
    write_review_report(report_path, version, snapshot, first)
    version.refresh_from_db()
    accepted = latest_accepted_alignment(version, trip)

    assert len(first.alignments) == 1
    assert first.alignments[0].status == "accepted"
    assert second.reused_count == 1
    assert second.alignments[0].id == first.alignments[0].id
    assert version.record_counts["matched_infrastructure_count"] == 1
    assert version.record_counts["matched_infrastructure_derived_at"].endswith("Z")
    assert accepted is not None
    assert json.loads(report_path.read_text(encoding="utf-8"))["trips"] == [
        {
            "map_url": "https://www.openstreetmap.org/#map=12/3.000000/101.004000",
            "metrics": first.alignments[0].metrics,
            "reason": "",
            "route_id": "KTM-1",
            "status": "accepted",
            "trip_id": "KTM-1-outbound",
        }
    ]

    invalidate_snapshot(snapshot, "Source review found an incorrect branch.")
    version.refresh_from_db()

    assert latest_accepted_alignment(version, trip) is None
    assert version.record_counts["matched_infrastructure_count"] == 0


def _snapshot_payload() -> dict[str, object]:
    return {
        "osm3s": {"timestamp_osm_base": "2026-08-23T00:00:00Z"},
        "elements": [
            {"type": "node", "id": 1, "lat": 3.0, "lon": 101.0},
            {"type": "node", "id": 2, "lat": 3.0, "lon": 101.004},
            {"type": "node", "id": 3, "lat": 3.0, "lon": 101.008},
            {
                "type": "way",
                "id": 100,
                "nodes": [1, 2, 3],
                "tags": {"railway": "rail", "operator": "KTM"},
            },
            {
                "type": "way",
                "id": 101,
                "nodes": [1, 3],
                "tags": {"railway": "rail", "service": "yard"},
            },
        ],
    }


def _xml_snapshot() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<osm version=\"0.6\" generator=\"Osmium\">
  <node id=\"1\" lat=\"3.0\" lon=\"101.0\" />
  <node id=\"2\" lat=\"3.0\" lon=\"101.004\" />
  <node id=\"3\" lat=\"3.0\" lon=\"101.008\" />
  <way id=\"100\">
    <nd ref=\"1\" />
    <nd ref=\"2\" />
    <nd ref=\"3\" />
    <tag k=\"railway\" v=\"rail\" />
    <tag k=\"operator\" v=\"KTM\" />
  </way>
</osm>
"""


def _scheduled_trip() -> tuple[StaticFeedVersion, GtfsTrip]:
    feed = TransitFeed.objects.create(
        display_name="KTMB",
        slug="ktmb",
        static_source_url="https://example.com/ktmb.zip",
    )
    version = StaticFeedVersion.objects.create(
        content_sha256="a" * 64,
        feed=feed,
        record_counts={
            "orphan_trip_shapes": 0,
            "trips": 1,
            "trips_with_shape": 0,
            "trips_without_shape": 1,
        },
        source_url=feed.static_source_url,
        status=StaticFeedVersion.Status.ACTIVE,
    )
    GtfsRoute.objects.create(feed_version=version, route_id="KTM-1", route_type=2)
    service = GtfsService.objects.create(
        end_date=date(2026, 12, 31),
        feed_version=version,
        friday=True,
        monday=True,
        saturday=True,
        service_id="daily",
        start_date=date(2026, 1, 1),
        sunday=True,
        thursday=True,
        tuesday=True,
        wednesday=True,
    )
    trip = GtfsTrip.objects.create(
        feed_version=version,
        headsign="KTM-1",
        route_id="KTM-1",
        service_id=service.service_id,
        trip_id="KTM-1-outbound",
    )
    for sequence, (stop_id, longitude) in enumerate(
        (("S1", "101.000000"), ("S2", "101.004000"), ("S3", "101.008000"))
    ):
        GtfsStop.objects.create(
            feed_version=version,
            latitude="3.000000",
            longitude=longitude,
            name=stop_id,
            stop_id=stop_id,
        )
        GtfsStopTime.objects.create(
            arrival_time=f"08:{sequence}0:00",
            departure_time=f"08:{sequence}0:00",
            stop_id=stop_id,
            stop_sequence=sequence,
            trip=trip,
        )
    return version, trip
