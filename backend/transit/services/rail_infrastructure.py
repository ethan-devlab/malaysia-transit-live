"""Import and query immutable, attributable rail-infrastructure snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import TypeGuard, cast
from xml.etree import ElementTree as ET

from django.db import transaction
from django.utils import timezone

from transit.models import (
    DerivedTripAlignment,
    GtfsTrip,
    RailInfrastructureEdge,
    RailInfrastructureNode,
    RailInfrastructureSnapshot,
    StaticFeedVersion,
)
from transit.services.rail_matching import GraphEdge, GraphNode, RailGraph, haversine_metres

GRAPH_SCHEMA_VERSION = "osm-way-graph-v1"
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"
OSM_LICENCE = "Open Data Commons Open Database License (ODbL) v1.0"
PERMITTED_RAILWAY_KINDS = frozenset(("rail", "narrow_gauge"))
IMPORT_BATCH_SIZE = 1_000
type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]
type JsonObject = dict[str, JsonValue]


class InfrastructureImportError(ValueError):
    """Report a source payload that cannot become a permitted railway graph."""


@dataclass(frozen=True, slots=True)
class ParsedRailNode:
    """Represent one normalized source vertex before it receives a database ID."""

    external_id: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class ParsedRailEdge:
    """Represent one normalized, permitted source segment before persistence."""

    external_id: str
    start_node_external_id: str
    end_node_external_id: str
    railway_kind: str
    route_refs: tuple[str, ...]
    length_metres: int


@dataclass(frozen=True, slots=True)
class ParsedRailGraph:
    """Carry validated graph records and immutable source metadata into one import."""

    nodes: tuple[ParsedRailNode, ...]
    edges: tuple[ParsedRailEdge, ...]
    geographic_extent: dict[str, float]
    source_captured_at: datetime | None


def import_rail_snapshot(
    archive_path: Path,
    *,
    source_url: str,
    source_captured_at: datetime | None,
    provider_name: str = "OpenStreetMap",
    licence_name: str = OSM_LICENCE,
    attribution: str = OSM_ATTRIBUTION,
    attribution_url: str = OSM_ATTRIBUTION_URL,
) -> tuple[RailInfrastructureSnapshot, bool]:
    """Persist a local OSM XML or Overpass JSON graph without a network request."""
    archive_bytes = archive_path.read_bytes()
    content_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    existing = RailInfrastructureSnapshot.objects.filter(content_sha256=content_sha256).first()
    if existing is not None:
        return existing, False
    if archive_path.suffix.lower() == ".json":
        parsed = parse_overpass_rail_graph(cast("JsonObject", json.loads(archive_bytes)))
    elif archive_path.suffix.lower() in {".osm", ".xml"}:
        parsed = parse_osm_xml_rail_graph(archive_path)
    else:
        raise InfrastructureImportError("Snapshot must use a .json, .osm, or .xml file extension.")
    captured_at = source_captured_at or parsed.source_captured_at
    if captured_at is None:
        raise InfrastructureImportError(
            "The snapshot has no OSM timestamp. Supply --source-captured-at explicitly."
        )
    if timezone.is_naive(captured_at):
        captured_at = timezone.make_aware(captured_at, UTC)
    with transaction.atomic():
        snapshot = RailInfrastructureSnapshot.objects.create(
            attribution=attribution,
            attribution_url=attribution_url,
            content_sha256=content_sha256,
            geographic_extent=parsed.geographic_extent,
            graph_schema_version=GRAPH_SCHEMA_VERSION,
            licence_name=licence_name,
            provider_name=provider_name,
            source_captured_at=captured_at,
            source_url=source_url,
        )
        _persist_graph(snapshot, parsed)
    return snapshot, True


def import_overpass_snapshot(
    archive_path: Path,
    *,
    source_url: str,
    source_captured_at: datetime | None,
    provider_name: str = "OpenStreetMap",
    licence_name: str = OSM_LICENCE,
    attribution: str = OSM_ATTRIBUTION,
    attribution_url: str = OSM_ATTRIBUTION_URL,
) -> tuple[RailInfrastructureSnapshot, bool]:
    """Import a historical Overpass JSON snapshot through the shared offline contract."""
    return import_rail_snapshot(
        archive_path,
        attribution=attribution,
        attribution_url=attribution_url,
        licence_name=licence_name,
        provider_name=provider_name,
        source_captured_at=source_captured_at,
        source_url=source_url,
    )


def parse_overpass_rail_graph(payload: JsonObject) -> ParsedRailGraph:
    """Normalize permitted OSM railway ways into shared-node graph records."""
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise InfrastructureImportError("Expected an Overpass JSON object with an elements list.")
    elements = payload["elements"]
    if not isinstance(elements, list):
        raise InfrastructureImportError("Expected an Overpass JSON elements list.")
    return _parse_osm_elements(elements, _snapshot_timestamp(payload))


def parse_osm_xml_rail_graph(archive_path: Path) -> ParsedRailGraph:
    """Parse a filtered OSM XML archive into records for offline snapshot import."""
    elements: list[JsonObject] = []
    if b"<!DOCTYPE" in archive_path.read_bytes().upper():
        raise InfrastructureImportError("OSM XML snapshot must not declare a DTD.")
    try:
        for _, element in ET.iterparse(archive_path, events=("end",)):  # noqa: S314
            if element.tag == "node":
                elements.append(_xml_node(element))
                element.clear()
            elif element.tag == "way":
                elements.append(_xml_way(element))
                element.clear()
    except (ET.ParseError, ValueError) as error:
        raise InfrastructureImportError("OSM XML snapshot is malformed.") from error
    return _parse_osm_elements(elements, None)


def _parse_osm_elements(
    elements: list[JsonValue],
    source_captured_at: datetime | None,
) -> ParsedRailGraph:
    raw_nodes: dict[str, tuple[float, float]] = {}
    for element in elements:
        if _is_osm_node(element):
            raw_nodes[_node_external_id(element)] = (float(element["lat"]), float(element["lon"]))
    parsed_edges: list[ParsedRailEdge] = []
    used_node_ids: set[str] = set()
    for element in elements:
        if not _is_permitted_way(element):
            continue
        node_ids = tuple(_node_reference_external_id(node_id) for node_id in element["nodes"])
        if any(node_id not in raw_nodes for node_id in node_ids):
            continue
        tags = element.get("tags", {})
        railway_kind = str(tags["railway"])
        route_refs = _route_refs(tags)
        for sequence, (start_node_id, end_node_id) in enumerate(pairwise(node_ids)):
            start = raw_nodes[start_node_id]
            end = raw_nodes[end_node_id]
            length_metres = max(1, round(haversine_metres(_lon_lat(start), _lon_lat(end))))
            parsed_edges.append(
                ParsedRailEdge(
                    end_node_external_id=end_node_id,
                    external_id=f"osm-way:{element['id']}:{sequence}",
                    length_metres=length_metres,
                    railway_kind=railway_kind,
                    route_refs=route_refs,
                    start_node_external_id=start_node_id,
                )
            )
            used_node_ids.update((start_node_id, end_node_id))
    if not parsed_edges:
        raise InfrastructureImportError("The snapshot has no permitted railway segments.")
    nodes = tuple(
        ParsedRailNode(
            external_id=node_id,
            latitude=raw_nodes[node_id][0],
            longitude=raw_nodes[node_id][1],
        )
        for node_id in sorted(used_node_ids)
    )
    return ParsedRailGraph(
        edges=tuple(parsed_edges),
        geographic_extent=_geographic_extent(nodes),
        nodes=nodes,
        source_captured_at=source_captured_at,
    )


def railway_graph(snapshot: RailInfrastructureSnapshot) -> RailGraph:
    """Load one persisted snapshot into an in-memory graph for an offline command."""
    nodes = {
        external_id: GraphNode(
            external_id=external_id,
            coordinate=(float(longitude), float(latitude)),
        )
        for external_id, latitude, longitude in RailInfrastructureNode.objects.filter(
            snapshot=snapshot
        ).values_list("external_id", "latitude", "longitude")
    }
    edges = tuple(
        GraphEdge(
            end_node_external_id=end_node_external_id,
            external_id=external_id,
            length_metres=float(length_metres),
            route_refs=tuple(route_refs),
            start_node_external_id=start_node_external_id,
        )
        for (
            external_id,
            start_node_external_id,
            end_node_external_id,
            route_refs,
            length_metres,
        ) in RailInfrastructureEdge.objects.filter(snapshot=snapshot)
        .select_related("start_node", "end_node")
        .values_list(
            "external_id",
            "start_node__external_id",
            "end_node__external_id",
            "route_refs",
            "length_metres",
        )
    )
    return RailGraph.from_edges(nodes, edges)


def latest_accepted_alignment(
    version: StaticFeedVersion,
    trip: GtfsTrip,
) -> DerivedTripAlignment | None:
    """Return the newest valid accepted result while an older graph remains valid."""
    return (
        DerivedTripAlignment.objects.filter(
            snapshot__status=RailInfrastructureSnapshot.Status.IMPORTED,
            static_feed_version=version,
            status=DerivedTripAlignment.Status.ACCEPTED,
            trip=trip,
        )
        .select_related("snapshot")
        .order_by("-created_at", "-id")
        .first()
    )


def refresh_geometry_coverage(version: StaticFeedVersion) -> None:
    """Materialize version coverage after offline matching or invalidation only."""
    record_counts = dict(version.record_counts)
    trip_count = int(record_counts.get("trips", 0))
    trips_with_shape = int(record_counts.get("trips_with_shape", 0))
    orphan_trip_shapes = int(record_counts.get("orphan_trip_shapes", 0))
    official_shape_count = min(trip_count, max(0, trips_with_shape - orphan_trip_shapes))
    matched_infrastructure_count = min(
        max(0, trip_count - official_shape_count),
        DerivedTripAlignment.objects.filter(
            snapshot__status=RailInfrastructureSnapshot.Status.IMPORTED,
            static_feed_version=version,
            status=DerivedTripAlignment.Status.ACCEPTED,
        )
        .values("trip_id")
        .distinct()
        .count(),
    )
    derived_at = (
        DerivedTripAlignment.objects.filter(
            snapshot__status=RailInfrastructureSnapshot.Status.IMPORTED,
            static_feed_version=version,
            status=DerivedTripAlignment.Status.ACCEPTED,
        )
        .order_by("-created_at", "-id")
        .values_list("created_at", flat=True)
        .first()
    )
    record_counts.update(
        {
            "matched_infrastructure_count": matched_infrastructure_count,
            "matched_infrastructure_derived_at": (
                derived_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
                if derived_at
                else None
            ),
        }
    )
    version.record_counts = record_counts
    version.save(update_fields=("record_counts",))


def invalidate_snapshot(snapshot: RailInfrastructureSnapshot, reason: str) -> None:
    """Exclude a bad graph from resolution and refresh only affected versions."""
    affected_versions = tuple(
        StaticFeedVersion.objects.filter(derived_alignments__snapshot=snapshot).distinct()
    )
    snapshot.failure_reason = reason
    snapshot.invalidated_at = timezone.now()
    snapshot.status = RailInfrastructureSnapshot.Status.INVALID
    snapshot.save(update_fields=("failure_reason", "invalidated_at", "status"))
    for version in affected_versions:
        refresh_geometry_coverage(version)


def _persist_graph(snapshot: RailInfrastructureSnapshot, parsed: ParsedRailGraph) -> None:
    _persist_nodes(snapshot, parsed.nodes)
    node_ids = dict(
        RailInfrastructureNode.objects.filter(snapshot=snapshot).values_list("external_id", "id")
    )
    _persist_edges(snapshot, parsed.edges, node_ids)


def _persist_nodes(
    snapshot: RailInfrastructureSnapshot,
    nodes: tuple[ParsedRailNode, ...],
) -> None:
    batch: list[RailInfrastructureNode] = []
    for node in nodes:
        batch.append(
            RailInfrastructureNode(
                external_id=node.external_id,
                latitude=Decimal(f"{node.latitude:.6f}"),
                longitude=Decimal(f"{node.longitude:.6f}"),
                snapshot=snapshot,
            )
        )
        if len(batch) == IMPORT_BATCH_SIZE:
            RailInfrastructureNode.objects.bulk_create(batch, batch_size=IMPORT_BATCH_SIZE)
            batch.clear()
    if batch:
        RailInfrastructureNode.objects.bulk_create(batch, batch_size=IMPORT_BATCH_SIZE)


def _persist_edges(
    snapshot: RailInfrastructureSnapshot,
    edges: tuple[ParsedRailEdge, ...],
    node_ids: dict[str, int],
) -> None:
    batch: list[RailInfrastructureEdge] = []
    for edge in edges:
        batch.append(
            RailInfrastructureEdge(
                end_node_id=node_ids[edge.end_node_external_id],
                external_id=edge.external_id,
                length_metres=edge.length_metres,
                railway_kind=edge.railway_kind,
                route_refs=list(edge.route_refs),
                snapshot=snapshot,
                start_node_id=node_ids[edge.start_node_external_id],
            )
        )
        if len(batch) == IMPORT_BATCH_SIZE:
            RailInfrastructureEdge.objects.bulk_create(batch, batch_size=IMPORT_BATCH_SIZE)
            batch.clear()
    if batch:
        RailInfrastructureEdge.objects.bulk_create(batch, batch_size=IMPORT_BATCH_SIZE)


def _is_osm_node(element: JsonValue) -> TypeGuard[JsonObject]:
    return (
        isinstance(element, dict)
        and element.get("type") == "node"
        and isinstance(element.get("id"), int)
        and isinstance(element.get("lat"), (int, float))
        and isinstance(element.get("lon"), (int, float))
        and -90 <= element["lat"] <= 90
        and -180 <= element["lon"] <= 180
    )


def _xml_node(element: ET.Element[str]) -> JsonObject:
    return {
        "id": int(_required_xml_attribute(element, "id")),
        "lat": float(_required_xml_attribute(element, "lat")),
        "lon": float(_required_xml_attribute(element, "lon")),
        "type": "node",
    }


def _xml_way(element: ET.Element[str]) -> JsonObject:
    node_refs = [
        int(_required_xml_attribute(node, "ref"))
        for node in element.findall("nd")
    ]
    tags = {
        _required_xml_attribute(tag, "k"): _required_xml_attribute(tag, "v")
        for tag in element.findall("tag")
    }
    return {
        "id": int(_required_xml_attribute(element, "id")),
        "nodes": node_refs,
        "tags": tags,
        "type": "way",
    }


def _required_xml_attribute(element: ET.Element[str], name: str) -> str:
    value = element.get(name)
    if not value:
        raise ValueError(f"OSM XML {element.tag} is missing its {name} attribute.")
    return value


def _is_permitted_way(element: JsonValue) -> TypeGuard[JsonObject]:
    if not isinstance(element, dict) or element.get("type") != "way":
        return False
    tags = element.get("tags")
    return (
        isinstance(element.get("id"), int)
        and isinstance(element.get("nodes"), list)
        and len(element["nodes"]) >= 2
        and isinstance(tags, dict)
        and tags.get("railway") in PERMITTED_RAILWAY_KINDS
        and tags.get("service") not in {"siding", "spur", "yard"}
    )


def _node_external_id(element: JsonObject) -> str:
    return _node_reference_external_id(element["id"])


def _node_reference_external_id(node_id: JsonValue) -> str:
    if not isinstance(node_id, int):
        raise InfrastructureImportError("A railway way contains a non-integer node reference.")
    return f"osm-node:{node_id}"


def _route_refs(tags: JsonObject) -> tuple[str, ...]:
    values = [
        value
        for key in ("ref", "name", "operator", "network", "line")
        if isinstance((value := tags.get(key)), str) and value.strip()
    ]
    return tuple(
        sorted({part.strip() for value in values for part in value.split(";") if part.strip()})
    )


def _snapshot_timestamp(payload: JsonObject) -> datetime | None:
    osm3s = payload.get("osm3s")
    timestamp = osm3s.get("timestamp_osm_base") if isinstance(osm3s, dict) else None
    if not isinstance(timestamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise InfrastructureImportError("OSM snapshot timestamp is invalid.") from error
    return parsed.astimezone(UTC)


def _geographic_extent(nodes: tuple[ParsedRailNode, ...]) -> dict[str, float]:
    return {
        "max_latitude": max(node.latitude for node in nodes),
        "max_longitude": max(node.longitude for node in nodes),
        "min_latitude": min(node.latitude for node in nodes),
        "min_longitude": min(node.longitude for node in nodes),
    }


def _lon_lat(latitude_longitude: tuple[float, float]) -> tuple[float, float]:
    latitude, longitude = latitude_longitude
    return longitude, latitude
