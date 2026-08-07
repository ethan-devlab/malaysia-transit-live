import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("transit", "0004_transitfeed_dashboard_metadata")]

    operations = [
        migrations.CreateModel(
            name="GtfsShapePoint",
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
                ("shape_id", models.CharField(max_length=160)),
                ("sequence", models.PositiveIntegerField()),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9)),
                (
                    "distance_travelled",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=20,
                        null=True,
                    ),
                ),
                (
                    "feed_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shape_points",
                        to="transit.staticfeedversion",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["feed_version", "shape_id", "sequence"],
                        name="gtfs_shape_feed_shape_seq_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("feed_version", "shape_id", "sequence"),
                        name="unique_shape_point_per_static_version",
                    )
                ],
            },
        ),
    ]
