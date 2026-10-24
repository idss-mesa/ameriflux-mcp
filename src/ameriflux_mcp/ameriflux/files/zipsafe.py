"""Read zip archives without extracting them (DESIGN.md D23, D36).

Every member is judged from the central directory before a byte is decompressed:

* names that are absolute, carry a drive letter, or contain a ``..`` segment
  (``zip slip``) are refused;
* symbolic links and encrypted members are refused;
* members larger than ``limits.zip_member_max_bytes`` (1 GiB) are refused, and so is a
  member over 1 MiB whose compression ratio exceeds 200 (a zip bomb);
* reads count decompressed bytes and stop at the member's declared size or the cap,
  whichever is smaller, so a lying header cannot inflate past it.

Refused members are still listed, with the reason, so ``amf_list_files`` can say why a
file is unreadable. Nothing is ever written to disk.
"""

from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO

from ameriflux_mcp.errors import ToolError

MAX_RATIO = 200
RATIO_MIN_BYTES = 1024 * 1024
MAX_MEMBERS = 10_000


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    compressed: int
    refused: str | None = None

    @property
    def basename(self) -> str:
        return self.name.rsplit("/", 1)[-1]


def _refusal(info: zipfile.ZipInfo, max_bytes: int) -> str | None:
    name = info.filename
    parts = name.replace("\\", "/").split("/")
    if name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":") or ".." in parts:
        return "unsafe path (outside the archive)"
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return "symbolic link"
    if info.flag_bits & 0x1:
        return "encrypted"
    if info.file_size > max_bytes:
        return f"larger than {max_bytes} bytes uncompressed"
    if info.file_size > RATIO_MIN_BYTES and (
        info.compress_size == 0 or info.file_size / info.compress_size > MAX_RATIO
    ):
        return f"compression ratio above {MAX_RATIO} (possible zip bomb)"
    return None


class CountingReader(io.RawIOBase):
    """A capped, counting view of one decompressed member."""

    def __init__(self, raw: IO[bytes], limit: int, label: str) -> None:
        self._raw = raw
        self._limit = limit
        self._label = label
        self.count = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        data = self._raw.read(len(buffer))
        self.count += len(data)
        if self.count > self._limit:
            raise ToolError(
                "invalid_argument",
                f"{self._label} decompresses past its declared size; refusing to read further.",
                details={"reason": "member_overrun", "member": self._label},
            )
        buffer[: len(data)] = data
        return len(data)

    def close(self) -> None:
        self._raw.close()
        super().close()


class SafeZip:
    """A read-only zip archive whose members are vetted before use."""

    def __init__(self, source: Path | bytes, *, max_member_bytes: int, label: str = "") -> None:
        self.label = label or (source.name if isinstance(source, Path) else "archive")
        self.max_member_bytes = max_member_bytes
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(source) if isinstance(source, bytes) else source)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ToolError(
                "invalid_argument",
                f"{self.label} is not a readable zip archive.",
                details={"reason": "bad_zip", "error": type(exc).__name__},
            ) from None
        infos = [i for i in self._zip.infolist() if not i.is_dir()]
        if len(infos) > MAX_MEMBERS:
            self._zip.close()
            raise ToolError(
                "invalid_argument",
                f"{self.label} has more than {MAX_MEMBERS} members.",
                details={"reason": "too_many_members", "members": len(infos)},
            )
        self._infos = {i.filename: i for i in infos}
        self.members = [
            Member(i.filename, i.file_size, i.compress_size, _refusal(i, max_member_bytes))
            for i in infos
        ]

    def __enter__(self) -> SafeZip:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    def member(self, name: str) -> Member:
        """A member by exact name or, failing that, by basename (case-insensitive)."""
        for m in self.members:
            if m.name == name:
                return m
        folded = name.rsplit("/", 1)[-1].casefold()
        matches = [m for m in self.members if m.basename.casefold() == folded]
        if len(matches) == 1:
            return matches[0]
        raise ToolError(
            "not_found",
            f"{self.label} has no member {name!r}.",
            details={"members": [m.name for m in self.members][:50]},
        )

    def open(self, name: str) -> CountingReader:
        member = self.member(name)
        if member.refused:
            raise ToolError(
                "invalid_argument",
                f"{self.label}::{member.name} is refused: {member.refused}.",
                details={"reason": "unsafe_member", "member": member.name, "why": member.refused},
            )
        info = self._infos[member.name]
        limit = min(info.file_size, self.max_member_bytes)
        return CountingReader(self._zip.open(info), limit, f"{self.label}::{member.name}")

    def read(self, name: str) -> bytes:
        with self.open(name) as reader:
            return reader.read()


__all__ = ["MAX_RATIO", "CountingReader", "Member", "SafeZip"]
