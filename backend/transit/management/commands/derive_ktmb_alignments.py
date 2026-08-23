"""Build and report bounded KTMB derivations from an existing rail graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from transit.models import (
    DerivedTripAlignment,
    RailInfrastructureSnapshot,
    StaticFeedVersion,
    TransitFeed,
)
from transit.services.rail_alignment import derive_alignments, write_review_report


class Command(BaseCommand):
    """Run matching outside public request paths and emit a reviewable report."""

    help = "Derive and report constrained KTMB rail alignments from an imported graph snapshot."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--snapshot",
            required=True,
            type=int,
            help="Imported graph snapshot ID.",
        )
        parser.add_argument(
            "--report",
            required=True,
            help="Output path for the bounded JSON review report.",
        )
        parser.add_argument(
            "--feed",
            default="ktmb",
            help="Active static feed slug; defaults to ktmb.",
        )

    def handle(self, *args: Any, **options: Any) -> str:
        try:
            feed = TransitFeed.objects.get(slug=options["feed"])
            version = StaticFeedVersion.objects.get(
                feed=feed,
                status=StaticFeedVersion.Status.ACTIVE,
            )
            snapshot = RailInfrastructureSnapshot.objects.get(pk=options["snapshot"])
        except (
            RailInfrastructureSnapshot.DoesNotExist,
            StaticFeedVersion.DoesNotExist,
            TransitFeed.DoesNotExist,
        ) as error:
            message = "The requested active feed or infrastructure snapshot does not exist."
            raise CommandError(message) from error
        try:
            run = derive_alignments(version, snapshot)
        except ValueError as error:
            raise CommandError(str(error)) from error
        report_path = Path(options["report"])
        write_review_report(report_path, version, snapshot, run)
        counts = {
            status: sum(alignment.status == status for alignment in run.alignments)
            for status in DerivedTripAlignment.Status.values
        }
        return self.style.SUCCESS(
            f"Derived {counts['accepted']} accepted, {counts['ambiguous']} ambiguous, and "
            f"{counts['rejected']} rejected alignment(s); report: {report_path}"
        )
