"""Bounded archive and CSV readers for untrusted GTFS ZIP files."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path

from transit.services.static_import.contracts import ArchiveInspection, StaticImportError

MAX_ARCHIVE_BYTES = 300 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 800 * 1024 * 1024
MAX_MEMBER_BYTES = 180 * 1024 * 1024
MAX_MEMBERS = 80


def inspect_archive(archive_path: Path) -> ArchiveInspection:
    """Validate a local ZIP before opening any CSV member."""
    if not archive_path.is_file():
        raise StaticImportError("archive_missing", "Archive path does not exist.", "archive")
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise StaticImportError(
            "archive_too_large", "Archive exceeds the compressed size limit.", "archive"
        )

    content_sha256 = _sha256_file(archive_path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > MAX_MEMBERS:
                raise StaticImportError(
                    "too_many_members", "Archive has too many members.", "archive"
                )

            total_uncompressed = sum(member.file_size for member in members)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise StaticImportError(
                    "archive_too_large",
                    "Archive exceeds the uncompressed size limit.",
                    "archive",
                )

            _validate_members(members)
            manifest = {
                "files": [
                    {"name": member.filename, "size_bytes": member.file_size} for member in members
                ],
                "sha256": content_sha256,
                "uncompressed_size_bytes": total_uncompressed,
            }
    except zipfile.BadZipFile as error:
        raise StaticImportError(
            "malformed_zip", "Archive is not a valid ZIP file.", "archive"
        ) from error

    return ArchiveInspection(content_sha256=content_sha256, manifest=manifest)


def has_member(archive: zipfile.ZipFile, filename: str) -> bool:
    """Return whether the top-level GTFS file exists in an inspected archive."""
    return filename in archive.namelist()


def iter_rows(
    archive: zipfile.ZipFile,
    filename: str,
    required_columns: Sequence[str],
) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield normalized UTF-8 GTFS rows while enforcing required headers."""
    if not has_member(archive, filename):
        raise StaticImportError("missing_file", f"Required file {filename} is missing.", filename)

    with archive.open(filename) as member:
        text_stream = io.TextIOWrapper(member, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_stream)
        headers = tuple(header.strip() for header in reader.fieldnames or () if header)
        missing_columns = sorted(set(required_columns).difference(headers))
        if missing_columns:
            missing_text = ", ".join(missing_columns)
            raise StaticImportError(
                "missing_column",
                f"Required columns are missing: {missing_text}.",
                filename,
            )

        for row_number, raw_row in enumerate(reader, start=2):
            row = {key.strip(): (value or "").strip() for key, value in raw_row.items() if key}
            yield row_number, row


def _sha256_file(archive_path: Path) -> str:
    hasher = hashlib.sha256()
    with archive_path.open("rb") as archive_file:
        for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _validate_members(members: Sequence[zipfile.ZipInfo]) -> None:
    for member in members:
        if member.file_size > MAX_MEMBER_BYTES:
            raise StaticImportError(
                "member_too_large",
                f"Archive member {member.filename} exceeds the member size limit.",
                "archive",
            )
        if member.filename.startswith(("/", "\\")) or ".." in Path(member.filename).parts:
            raise StaticImportError(
                "unsafe_member_path",
                f"Archive member {member.filename} has an unsafe path.",
                "archive",
            )
        if member.compress_size == 0 and member.file_size > 0:
            raise StaticImportError(
                "suspicious_member",
                f"Archive member {member.filename} has an invalid compressed size.",
                "archive",
            )
