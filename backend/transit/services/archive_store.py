"""Archive-store selection for local filesystem and Cloudflare R2 runtimes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Final

from transit.services.archive_contracts import (
    ArchiveConfigurationError,
    ArchiveStorageError,
    ArchiveStore,
)
from transit.services.r2_archive import R2ArchiveStore

ARCHIVE_BACKEND_ENV: Final = "TRANSIT_ARCHIVE_BACKEND"
ARCHIVE_DIRECTORY_ENV: Final = "TRANSIT_ARCHIVE_DIRECTORY"


def archive_store_from_environment() -> ArchiveStore:
    """Build the explicitly selected archive backend for the current runtime."""
    backend = os.environ.get(ARCHIVE_BACKEND_ENV, "r2").strip().lower()
    match backend:
        case "filesystem":
            return FilesystemArchiveStore.from_environment()
        case "r2":
            return R2ArchiveStore.from_environment()
        case _:
            raise ArchiveConfigurationError(f"Unsupported GTFS archive backend: {backend}.")


class FilesystemArchiveStore:
    """Keep local-only GTFS ZIPs in a mounted host directory."""

    def __init__(self, root_directory: Path) -> None:
        self._root_directory = root_directory

    @classmethod
    def from_environment(cls) -> FilesystemArchiveStore:
        """Load the private local archive directory from runtime configuration."""
        raw_directory = os.environ.get(ARCHIVE_DIRECTORY_ENV, "")
        if not raw_directory:
            raise ArchiveConfigurationError(
                f"Filesystem archive configuration is missing: {ARCHIVE_DIRECTORY_ENV}."
            )
        return cls(Path(raw_directory))

    def put_zip(self, archive_path: Path, object_key: str) -> None:
        """Copy an inspected ZIP into the mounted local archive directory."""
        destination = self._destination(object_key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive_path, destination)
        except OSError as error:
            raise ArchiveStorageError(
                "Unable to preserve the original GTFS ZIP locally."
            ) from error

    def delete_zip(self, object_key: str) -> None:
        """Remove one no-longer-retained local ZIP if it still exists."""
        destination = self._destination(object_key)
        try:
            destination.unlink(missing_ok=True)
        except OSError as error:
            raise ArchiveStorageError("Unable to remove an obsolete local GTFS ZIP.") from error

    def _destination(self, object_key: str) -> Path:
        archive_path = PurePosixPath(object_key)
        if not object_key or archive_path.is_absolute() or ".." in archive_path.parts:
            raise ArchiveStorageError("The GTFS archive key is unsafe for local storage.")
        return self._root_directory.joinpath(*archive_path.parts)
