"""Import a local, attributable OpenStreetMap rail snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from transit.services.rail_infrastructure import InfrastructureImportError, import_rail_snapshot


class Command(BaseCommand):
    """Expose the offline snapshot import as an idempotent operator command."""

    help = "Import a previously downloaded OSM railway XML or Overpass JSON snapshot."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--archive", required=True, help="Local OSM XML or Overpass JSON path.")
        parser.add_argument(
            "--source-url",
            required=True,
            help="Original OSM query or extract URL.",
        )
        parser.add_argument(
            "--source-captured-at",
            help="UTC ISO 8601 source timestamp; required for XML extracts.",
        )

    def handle(self, *args: Any, **options: Any) -> str:
        archive_path = Path(options["archive"])
        if not archive_path.is_file():
            raise CommandError(f"Snapshot file does not exist: {archive_path}")
        try:
            snapshot, created = import_rail_snapshot(
                archive_path,
                source_captured_at=_parse_timestamp(options["source_captured_at"]),
                source_url=options["source_url"],
            )
        except (InfrastructureImportError, OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        state = "Imported" if created else "Already imported"
        return self.style.SUCCESS(
            f"{state} snapshot {snapshot.id} ({snapshot.content_sha256}) with "
            f"{snapshot.nodes.count()} nodes and {snapshot.edges.count()} rail segments."
        )


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CommandError("--source-captured-at must be an ISO 8601 timestamp.") from error
    return parsed.astimezone(UTC)
