"""Persist immutable rail snapshots and their derived-alignment audit trail."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from transit.models.feed import StaticFeedVersion
from transit.models.gtfs import GtfsTrip


class RailInfrastructureSnapshot(models.Model):
    class Status(models.TextChoices):
        IMPORTED = "imported", "Imported"
        INVALID = "invalid", "Invalid"

    provider_name = models.CharField(max_length=160)
    source_url = models.URLField()
    source_captured_at = models.DateTimeField()
    geographic_extent = models.JSONField(default=dict)
    licence_name = models.CharField(max_length=160)
    attribution = models.CharField(max_length=255)
    attribution_url = models.URLField()
    content_sha256 = models.CharField(max_length=64, unique=True)
    graph_schema_version = models.CharField(max_length=80)
    status = models.CharField(max_length=16, choices=Status, default=Status.IMPORTED)
    imported_at = models.DateTimeField(auto_now_add=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=512, blank=True)

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=("status", "source_captured_at"),
                name="transit_rai_status_b12f80_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.content_sha256[:12]} ({self.status})"


class RailInfrastructureNode(models.Model):
    snapshot = models.ForeignKey(
        RailInfrastructureSnapshot,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    external_id = models.CharField(max_length=160)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("snapshot", "external_id"),
                name="unique_rail_node_per_snapshot",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=("snapshot", "latitude", "longitude"),
                name="transit_rai_snapsho_62f618_idx",
            ),
        ]


class RailInfrastructureEdge(models.Model):
    snapshot = models.ForeignKey(
        RailInfrastructureSnapshot,
        on_delete=models.CASCADE,
        related_name="edges",
    )
    external_id = models.CharField(max_length=200)
    start_node = models.ForeignKey(
        RailInfrastructureNode,
        on_delete=models.CASCADE,
        related_name="outgoing_edges",
    )
    end_node = models.ForeignKey(
        RailInfrastructureNode,
        on_delete=models.CASCADE,
        related_name="incoming_edges",
    )
    railway_kind = models.CharField(max_length=32)
    route_refs = models.JSONField(default=list)
    length_metres = models.PositiveIntegerField()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("snapshot", "external_id"),
                name="unique_rail_edge_per_snapshot",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=("snapshot", "start_node"),
                name="transit_rai_snapsho_3bc5ce_idx",
            ),
            models.Index(
                fields=("snapshot", "end_node"),
                name="transit_rai_snapsho_0a6331_idx",
            ),
        ]


class DerivedTripAlignment(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        AMBIGUOUS = "ambiguous", "Ambiguous"

    static_feed_version = models.ForeignKey(
        StaticFeedVersion,
        on_delete=models.CASCADE,
        related_name="derived_alignments",
    )
    trip = models.ForeignKey(
        GtfsTrip,
        on_delete=models.CASCADE,
        related_name="derived_alignments",
    )
    snapshot = models.ForeignKey(
        RailInfrastructureSnapshot,
        on_delete=models.CASCADE,
        related_name="derived_alignments",
    )
    status = models.CharField(max_length=16, choices=Status)
    derivation_version = models.CharField(max_length=80)
    matcher_config_sha256 = models.CharField(max_length=64)
    coordinates = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)
    reason = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=(
                    "static_feed_version",
                    "trip",
                    "snapshot",
                    "derivation_version",
                    "matcher_config_sha256",
                ),
                name="unique_derived_alignment_for_versioned_inputs",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=("static_feed_version", "trip", "status"),
                name="transit_der_static__a2d9f1_idx",
            ),
            models.Index(
                fields=("snapshot", "status"),
                name="transit_der_snapsho_eb2f5b_idx",
            ),
        ]
