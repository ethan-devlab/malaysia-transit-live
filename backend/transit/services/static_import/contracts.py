"""Typed contracts for the static GTFS importer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class StaticImportError(ValueError):
    """A validation failure tied to one archive file and, where known, one row."""

    def __init__(
        self,
        code: str,
        detail: str,
        source_file: str,
        row_number: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.source_file = source_file
        self.row_number = row_number


@dataclass(frozen=True)
class ArchiveInspection:
    """Archive metadata retained in the version manifest."""

    content_sha256: str
    manifest: Mapping[str, object]


@dataclass(frozen=True)
class StaticImportResult:
    """The immutable version created or rejected by an import attempt."""

    version_id: str
    status: str
    record_counts: Mapping[str, int]
    archive_path: Path
