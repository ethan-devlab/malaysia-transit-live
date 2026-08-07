"""Shared archive persistence contract and configuration errors."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArchiveConfigurationError(RuntimeError):
    """Raised when the selected archive backend lacks required configuration."""


class ArchiveStorageError(RuntimeError):
    """Raised when an archive cannot be persisted or removed safely."""


class ArchiveStore(Protocol):
    """Persist immutable GTFS ZIPs outside the relational dataset."""

    def put_zip(self, archive_path: Path, object_key: str) -> None:
        """Persist one inspected source ZIP under its stable object key."""

    def delete_zip(self, object_key: str) -> None:
        """Remove one obsolete source ZIP without touching active data."""
