import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("transit", "0005_gtfsshapepoint")]

    operations = [
        migrations.CreateModel(
            name="RailInfrastructureSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("provider_name", models.CharField(max_length=160)),
                ("source_url", models.URLField()),
                ("source_captured_at", models.DateTimeField()),
                ("geographic_extent", models.JSONField(default=dict)),
                ("licence_name", models.CharField(max_length=160)),
                ("attribution", models.CharField(max_length=255)),
                ("attribution_url", models.URLField()),
                ("content_sha256", models.CharField(max_length=64, unique=True)),
                ("graph_schema_version", models.CharField(max_length=80)),
                (
                    "status",
                    models.CharField(
                        choices=[("imported", "Imported"), ("invalid", "Invalid")],
                        default="imported",
                        max_length=16,
                    ),
                ),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.CharField(blank=True, max_length=512)),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["status", "source_captured_at"],
                        name="transit_rai_status_b12f80_idx",
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="RailInfrastructureNode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("external_id", models.CharField(max_length=160)),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9)),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nodes",
                        to="transit.railinfrastructuresnapshot",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["snapshot", "latitude", "longitude"],
                        name="transit_rai_snapsho_62f618_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("snapshot", "external_id"), name="unique_rail_node_per_snapshot"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="RailInfrastructureEdge",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("external_id", models.CharField(max_length=200)),
                ("railway_kind", models.CharField(max_length=32)),
                ("route_refs", models.JSONField(default=list)),
                ("length_metres", models.PositiveIntegerField()),
                (
                    "end_node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incoming_edges",
                        to="transit.railinfrastructurenode",
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="edges",
                        to="transit.railinfrastructuresnapshot",
                    ),
                ),
                (
                    "start_node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outgoing_edges",
                        to="transit.railinfrastructurenode",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["snapshot", "start_node"],
                        name="transit_rai_snapsho_3bc5ce_idx",
                    ),
                    models.Index(
                        fields=["snapshot", "end_node"],
                        name="transit_rai_snapsho_0a6331_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("snapshot", "external_id"), name="unique_rail_edge_per_snapshot"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DerivedTripAlignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("accepted", "Accepted"),
                            ("rejected", "Rejected"),
                            ("ambiguous", "Ambiguous"),
                        ],
                        max_length=16,
                    ),
                ),
                ("derivation_version", models.CharField(max_length=80)),
                ("matcher_config_sha256", models.CharField(max_length=64)),
                ("coordinates", models.JSONField(default=list)),
                ("metrics", models.JSONField(default=dict)),
                ("reason", models.CharField(blank=True, max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="derived_alignments",
                        to="transit.railinfrastructuresnapshot",
                    ),
                ),
                (
                    "static_feed_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="derived_alignments",
                        to="transit.staticfeedversion",
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="derived_alignments",
                        to="transit.gtfstrip",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["static_feed_version", "trip", "status"],
                        name="transit_der_static__a2d9f1_idx",
                    ),
                    models.Index(
                        fields=["snapshot", "status"],
                        name="transit_der_snapsho_eb2f5b_idx",
                    ),
                ],
                "constraints": [
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
                ],
            },
        ),
    ]
