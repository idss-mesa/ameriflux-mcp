"""Where the local file tools may read: the download directory and ``local.roots`` (D36).

A file argument is a path, absolute or relative to the first root, optionally followed
by ``::member`` to name a zip member (``AMF_US-Ha1_BASE-BADM_28-5.zip::AMF_US-Ha1_BASE_HR_28-5.csv``).
The path is resolved with symlinks followed and must land inside a root and be a regular
file; anything else is ``invalid_argument`` (``reason: outside_local_roots``) without
revealing whether the path exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ameriflux_mcp.config import Config
from ameriflux_mcp.errors import ToolError

MEMBER_SEPARATOR = "::"


@dataclass(frozen=True)
class LocalPath:
    path: Path
    root: Path
    member: str | None = None

    @property
    def relative(self) -> str:
        return self.path.relative_to(self.root).as_posix()

    @property
    def display(self) -> str:
        return self.relative + (f"{MEMBER_SEPARATOR}{self.member}" if self.member else "")


def roots(config: Config) -> list[Path]:
    """The download directory first, then ``local.roots``, de-duplicated, resolved."""
    out: list[Path] = []
    for root in (config.downloads.directory, *config.local.roots):
        resolved = root.expanduser().resolve()
        if resolved not in out:
            out.append(resolved)
    return out


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _outside(text: str) -> ToolError:
    return ToolError(
        "invalid_argument",
        "The file must be inside the download directory or a configured local root.",
        details={"reason": "outside_local_roots", "input": text[:300]},
        hint="List readable files with amf_list_files; add folders with AMERIFLUX_MCP_LOCAL__ROOTS.",
    )


def resolve_file(text: str, config: Config) -> LocalPath:
    """``path[::member]`` -> a confined :class:`LocalPath` (the file must exist)."""
    raw, _, member = text.strip().partition(MEMBER_SEPARATOR)
    if not raw:
        raise _outside(text)
    allowed = roots(config)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = allowed[0] / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise _outside(text) from None
    for root in allowed:
        if inside(resolved, root):
            if not resolved.is_file():
                raise _outside(text)
            return LocalPath(resolved, root, member.strip() or None)
    raise _outside(text)


def resolve_dir(text: str | None, config: Config) -> list[tuple[Path, Path]]:
    """(directory, root) pairs to list: every existing root, or one confined directory."""
    allowed = roots(config)
    if text is None or not text.strip():
        return [(r, r) for r in allowed if r.is_dir()]
    candidate = Path(text.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = allowed[0] / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise _outside(text) from None
    for root in allowed:
        if inside(resolved, root) and resolved.is_dir():
            return [(resolved, root)]
    raise _outside(text)


__all__ = ["MEMBER_SEPARATOR", "LocalPath", "inside", "resolve_dir", "resolve_file", "roots"]
