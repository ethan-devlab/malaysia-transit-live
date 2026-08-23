"""Invalidate one graph snapshot so only safely attributable paths resolve."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from transit.models import RailInfrastructureSnapshot
from transit.services.rail_infrastructure import invalidate_snapshot


class Command(BaseCommand):
    """Expose explicit operator invalidation rather than a silent provenance change."""

    help = "Invalidate an infrastructure snapshot so its derived alignments safely fall back."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--snapshot",
            required=True,
            type=int,
            help="Infrastructure snapshot ID.",
        )
        parser.add_argument(
            "--reason",
            required=True,
            help="Bounded operator reason for invalidation.",
        )

    def handle(self, *args: Any, **options: Any) -> str:
        try:
            snapshot = RailInfrastructureSnapshot.objects.get(pk=options["snapshot"])
        except RailInfrastructureSnapshot.DoesNotExist as error:
            raise CommandError("The requested infrastructure snapshot does not exist.") from error
        invalidate_snapshot(snapshot, options["reason"])
        return self.style.SUCCESS(f"Invalidated snapshot {snapshot.id}.")
