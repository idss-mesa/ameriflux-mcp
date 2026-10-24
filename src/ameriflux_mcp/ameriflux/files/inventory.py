"""Find AmeriFlux and FLUXNET files under the local roots (D36).

Walks the download directory and ``local.roots`` (symlinks are not followed, hidden
directories are skipped, at most :data:`MAX_FILES` names are examined), classifies each
name and, for archives, each member. :func:`pick_table` chooses the member a preview of
``{site, product, resolution}`` should read.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ameriflux_mcp.ameriflux.files.filenames import FileName, classify
from ameriflux_mcp.ameriflux.files.zipsafe import Member, SafeZip
from ameriflux_mcp.errors import ToolError

MAX_FILES = 20_000
MAX_DEPTH = 6


@dataclass(frozen=True)
class Found:
    path: Path
    root: Path
    name: FileName
    size: int
    mtime: float

    @property
    def relative(self) -> str:
        return self.path.relative_to(self.root).as_posix()


@dataclass
class Walk:
    found: list[Found]
    examined: int
    unrecognized: int
    capped: bool


def walk(dirs: list[tuple[Path, Path]]) -> Walk:
    found: list[Found] = []
    examined = unrecognized = 0
    capped = False
    for directory, root in dirs:
        base_depth = len(directory.parts)
        for current, subdirs, files in os.walk(directory, followlinks=False):
            depth = len(Path(current).parts) - base_depth
            subdirs[:] = sorted(d for d in subdirs if not d.startswith(".") and depth < MAX_DEPTH)
            for filename in sorted(files):
                examined += 1
                if examined > MAX_FILES:
                    capped = True
                    break
                path = Path(current) / filename
                if path.is_symlink() or not path.is_file():
                    continue
                name = classify(filename)
                if name is None:
                    unrecognized += 1
                    continue
                stat = path.stat()
                found.append(Found(path, root, name, stat.st_size, stat.st_mtime))
            if capped:
                break
    return Walk(found, examined, unrecognized, capped)


def version_key(name: FileName) -> tuple[int, ...]:
    """``28-5`` -> (28, 5); ``v1.3_r1`` -> (1, 3, 1); unknown -> ()."""
    return tuple(int(n) for n in re.findall(r"\d+", name.version or ""))


def classified_members(archive: SafeZip) -> Iterator[tuple[Member, FileName | None]]:
    for member in archive.members:
        yield member, classify(member.basename)


def pick_table(archive: SafeZip, container: FileName, resolution: str | None) -> Member:
    """The data member a preview of this archive reads by default."""
    res = (resolution or "HH").upper()
    wanted_res = {"HH": ("HH", "HR"), "HR": ("HR", "HH")}.get(res, (res,))
    candidates: list[tuple[int, Member]] = []
    for member, name in classified_members(archive):
        if name is None or name.kind != "data" or member.refused:
            continue
        if container.family == "base" or name.resolution in wanted_res:
            rank = 0 if name.variant in (None, "FLUXMET", "FULLSET") else 1
            candidates.append((rank, member))
    if not candidates:
        raise ToolError(
            "not_found",
            f"{container.name} has no readable data file at {res}.",
            details={
                "reason": "no_member",
                "members": [m.name for m in archive.members][:50],
            },
            hint="Name the member with file='archive.zip::member.csv'.",
        )
    return sorted(candidates, key=lambda c: (c[0], c[1].name))[0][1]


def pick_bif(archive: SafeZip) -> Member | None:
    """The BIF member of a BASE-BADM (xlsx) or FLUXNET (CSV) archive."""
    for member, name in classified_members(archive):
        if name is not None and name.kind == "bif" and not member.refused:
            return member
    return None


__all__ = [
    "MAX_FILES",
    "Found",
    "Walk",
    "classified_members",
    "pick_bif",
    "pick_table",
    "version_key",
    "walk",
]
