"""R2 archive persistence for original GTFS ZIPs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

from transit.services.archive_contracts import ArchiveConfigurationError, ArchiveStorageError


@dataclass(frozen=True)
class R2ArchiveSettings:
    """The minimal, server-only R2 connection information."""

    access_key_id: str
    bucket_name: str
    endpoint_url: str
    secret_access_key: str

    @classmethod
    def from_environment(cls) -> R2ArchiveSettings:
        """Load settings without logging credentials or endpoint query strings."""
        values = {
            "access_key_id": os.environ.get("R2_ACCESS_KEY_ID", ""),
            "bucket_name": os.environ.get("R2_GTFS_ARCHIVE_BUCKET", ""),
            "endpoint_url": os.environ.get("R2_ENDPOINT_URL", ""),
            "secret_access_key": os.environ.get("R2_SECRET_ACCESS_KEY", ""),
        }
        missing = sorted(field for field, value in values.items() if not value)
        if missing:
            missing_names = ", ".join(missing)
            raise ArchiveConfigurationError(f"R2 configuration is missing: {missing_names}.")
        return cls(**values)


class R2ArchiveStore:
    """Store immutable source archives with private server-side credentials."""

    def __init__(self, settings: R2ArchiveSettings) -> None:
        self._bucket_name = settings.bucket_name
        self._client = boto3.client(
            "s3",
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            endpoint_url=settings.endpoint_url,
            region_name="auto",
        )

    @classmethod
    def from_environment(cls) -> R2ArchiveStore:
        """Build the archive store only inside the backend worker process."""
        return cls(R2ArchiveSettings.from_environment())

    def put_zip(self, archive_path: Path, object_key: str) -> None:
        """Upload a source ZIP as a private binary archive."""
        try:
            self._client.upload_file(
                str(archive_path),
                self._bucket_name,
                object_key,
                ExtraArgs={"ContentType": "application/zip"},
            )
        except (BotoCoreError, ClientError, S3UploadFailedError) as error:
            raise ArchiveStorageError("Unable to archive the original GTFS ZIP in R2.") from error

    def delete_zip(self, object_key: str) -> None:
        """Remove a no-longer-retained source ZIP from the private R2 bucket."""
        try:
            self._client.delete_object(Bucket=self._bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as error:
            raise ArchiveStorageError("Unable to remove an obsolete GTFS ZIP from R2.") from error
