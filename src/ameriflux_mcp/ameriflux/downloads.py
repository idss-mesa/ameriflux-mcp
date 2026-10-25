"""Confined, verified transfers of ledger files (stdio only; DESIGN.md D15, D16, D18).

The download manager fetches only :class:`~ameriflux_mcp.ameriflux.ledger.LedgerEntry`
files, each re-checked against the ledger and the client's allow-list, into
``<downloads.directory>/<product>/<file name>``. Per file:

1. **HEAD** for Content-Length and ETag (only after the logged request; no previews);
2. the per-file and per-call caps, before any byte moves;
3. **GET** with ``If-Match`` (a hint: support is unverified) into ``<name>.part``,
   sha256 while writing;
4. the GET's ETag and Content-Length must equal HEAD's, and the byte count must equal
   Content-Length; zip and xlsx files must also open and pass every member's CRC
   (through :class:`~ameriflux_mcp.ameriflux.files.zipsafe.SafeZip`);
5. rename into place and write ``<name>.amf.json``, a sidecar with the checksum and
   provenance and no identity.

Any failure removes the ``.part`` file and leaves an existing file untouched.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ameriflux_mcp import __version__
from ameriflux_mcp.ameriflux.files.zipsafe import SafeZip
from ameriflux_mcp.ameriflux.ledger import NAME_RE, LedgerEntry
from ameriflux_mcp.errors import AmeriFluxApiError, ToolError, map_api_error
from ameriflux_mcp.logging import registered_secrets

if TYPE_CHECKING:
    from ameriflux_mcp.ameriflux.client import AmeriFluxClient
    from ameriflux_mcp.config import DownloadsConfig
    from ameriflux_mcp.context import UpstreamStats

SIDECAR_SUFFIX = ".amf.json"
SIDECAR_SCHEMA = "ameriflux-mcp/download-sidecar/1"
MANIFEST_SCHEMA = "ameriflux-mcp/download-manifest/1"
MANIFEST_DIR = "manifests"
PART_SUFFIX = ".part"
ARCHIVE_SUFFIXES = (".zip", ".xlsx")
FileStatus = Literal["downloaded", "skipped", "failed"]
IfExists = Literal["skip", "replace", "error"]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Head:
    length: int | None
    etag: str | None
    last_modified: str | None


@dataclass
class Outcome:
    """What happened to one ledger file."""

    entry: LedgerEntry
    path: Path
    status: FileStatus
    bytes: int | None = None
    sha256: str | None = None
    etag: str | None = None
    reason: str | None = None
    error: str | None = None
    identical: bool | None = None
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


def sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + SIDECAR_SUFFIX)


def read_sidecar(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def verify_archive(path: Path, *, max_member_bytes: int) -> list[str]:
    """Open a zip (or xlsx) and read every acceptable member, checking each CRC.

    Raises ``checksum_mismatch`` on a corrupt archive; returns notes on members the
    safe reader refuses (they are left unread, and the local tools refuse them too).
    """
    notes: list[str] = []
    try:
        with SafeZip(path, max_member_bytes=max_member_bytes, label=path.name) as archive:
            for member in archive.members:
                if member.refused:
                    notes.append(
                        f"{path.name}: member {member.name} is refused ({member.refused})."
                    )
                    continue
                with archive.open(member.name) as reader:
                    while reader.read(1 << 20):
                        pass
    except ToolError as exc:
        raise ToolError(
            "checksum_mismatch",
            f"{path.name} is not a readable archive; it was not kept.",
            details={"reason": "bad_archive", "file": path.name, "detail": exc.message},
        ) from None
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise ToolError(
            "checksum_mismatch",
            f"{path.name} failed its zip CRC check; it was not kept.",
            details={"reason": "bad_crc", "file": path.name, "error": type(exc).__name__},
        ) from None
    return notes


class DownloadManager:
    """Transfers for one call; every destination is under the download directory."""

    def __init__(
        self, config: DownloadsConfig, client: AmeriFluxClient, *, zip_member_max_bytes: int
    ) -> None:
        self.config = config
        self.client = client
        self.zip_member_max_bytes = zip_member_max_bytes

    @property
    def root(self) -> Path:
        return self.config.directory

    def destination(self, entry: LedgerEntry) -> Path:
        """``<root>/<product>/<name>``, refusing anything that could leave the root."""
        if not NAME_RE.match(entry.name) or not NAME_RE.match(entry.product):
            raise ToolError(
                "download_denied",
                "Refusing an unsafe file name.",
                details={"reason": "unsafe_name", "name": entry.name},
            )
        root = self.root
        candidate = root / entry.product / entry.name
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ToolError(
                "download_denied",
                "The destination escapes the download directory.",
                details={"reason": "outside_download_directory", "name": entry.name},
            )
        return resolved

    async def head(self, entry: LedgerEntry, *, stats: UpstreamStats) -> Head:
        self.client.ledger.require(entry.url)
        self.client.check_download_link(entry.url)
        try:
            fetched = await self.client.request("HEAD", entry.url, stats=stats)
        except AmeriFluxApiError as exc:
            raise map_api_error(exc, secrets=registered_secrets()) from None
        length = fetched.headers.get("content-length")
        return Head(
            length=int(length) if length and length.isdigit() else entry.download_size,
            etag=fetched.headers.get("etag"),
            last_modified=fetched.headers.get("last-modified"),
        )

    def existing(self, entry: LedgerEntry, path: Path, head: Head) -> bool | None:
        """Whether a file already at ``path`` is the one on the server (None: unknown)."""
        if not path.exists():
            return None
        size = path.stat().st_size
        sidecar = read_sidecar(path)
        if head.length is not None and size != head.length:
            return False
        if sidecar and head.etag and sidecar.get("etag"):
            return bool(sidecar.get("etag") == head.etag and sidecar.get("bytes") == size)
        return None  # same size, but nothing proves it is the same file

    async def fetch(
        self,
        entry: LedgerEntry,
        path: Path,
        head: Head,
        *,
        stats: UpstreamStats,
        sidecar: Mapping[str, Any],
    ) -> Outcome:
        """Stream one file into place and write its sidecar; failures become ``failed``."""
        started = time.monotonic()
        part = path.with_name(path.name + PART_SUFFIX)
        try:
            self.client.ledger.require(entry.url)
            self.client.check_download_link(entry.url)
            headers = {"If-Match": head.etag} if head.etag else None
            try:
                streamed = await self.client.stream_to_file(
                    entry.url,
                    part,
                    stats=stats,
                    max_bytes=self.config.max_file_bytes,
                    headers=headers,
                )
            except AmeriFluxApiError as exc:
                if exc.status == 412:
                    raise ToolError(
                        "checksum_mismatch",
                        f"{entry.name} changed on the server between HEAD and GET.",
                        details={"reason": "etag_changed", "file": entry.name},
                    ) from None
                raise map_api_error(exc, secrets=registered_secrets()) from None
            problems: dict[str, Any] = {}
            if head.etag and streamed.etag and streamed.etag != head.etag:
                problems["etag"] = {"head": head.etag, "get": streamed.etag}
            if head.length is not None and streamed.content_length not in (None, head.length):
                problems["contentLength"] = {"head": head.length, "get": streamed.content_length}
            expected = (
                streamed.content_length if streamed.content_length is not None else head.length
            )
            if expected is not None and streamed.bytes != expected:
                problems["bytes"] = {"expected": expected, "received": streamed.bytes}
            if problems:
                raise ToolError(
                    "checksum_mismatch",
                    f"{entry.name} does not match what the file server announced; it was not kept.",
                    details={"reason": "head_get_mismatch", "file": entry.name, **problems},
                    hint="Retry later; the file may have been replaced while downloading.",
                )
            notes: list[str] = []
            if entry.name.lower().endswith(ARCHIVE_SUFFIXES):
                notes = await asyncio.to_thread(
                    verify_archive, part, max_member_bytes=self.zip_member_max_bytes
                )
            os.replace(part, path)
            record = {
                "schema": SIDECAR_SCHEMA,
                "file": entry.name,
                "bytes": streamed.bytes,
                "sha256": streamed.sha256,
                "etag": streamed.etag or head.etag,
                "lastModified": head.last_modified,
                "url": entry.url,
                "siteId": entry.site_id or None,
                "product": entry.product,
                "dataProduct": entry.data_product or None,
                "policy": entry.policy,
                "requestId": entry.request_id,
                "downloadedAt": utc_now(),
                "tool": f"ameriflux-mcp/{__version__}",
                **dict(sidecar),
            }
            write_json(sidecar_path(path), record)
            return Outcome(
                entry=entry,
                path=path,
                status="downloaded",
                bytes=streamed.bytes,
                sha256=streamed.sha256,
                etag=record["etag"],
                seconds=round(time.monotonic() - started, 3),
                notes=notes,
            )
        except ToolError as exc:
            part.unlink(missing_ok=True)
            return Outcome(
                entry=entry,
                path=path,
                status="failed",
                reason=str(exc.details.get("reason") or exc.code),
                error=f"{exc.code}: {exc.message}",
                seconds=round(time.monotonic() - started, 3),
            )
        except BaseException:
            part.unlink(missing_ok=True)
            raise

    def free_bytes(self) -> int | None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            return shutil.disk_usage(self.root).free
        except OSError:
            return None


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Write ``data`` atomically (temporary file, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def manifest_path(root: Path, product: str, stamp: str) -> Path:
    safe = stamp.replace(":", "").replace("-", "")
    return root / MANIFEST_DIR / f"amf_download_{safe}_{product}.json"


__all__ = [
    "MANIFEST_DIR",
    "MANIFEST_SCHEMA",
    "SIDECAR_SCHEMA",
    "SIDECAR_SUFFIX",
    "DownloadManager",
    "FileStatus",
    "Head",
    "IfExists",
    "Outcome",
    "manifest_path",
    "read_sidecar",
    "sidecar_path",
    "utc_now",
    "verify_archive",
    "write_json",
]
