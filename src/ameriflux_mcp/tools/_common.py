"""Helpers shared by tool handlers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.models.common import Page, Source

T = TypeVar("T")


def source(ctx: ToolContext, *, derived: Sequence[str] = ()) -> Source:
    """The result's ``source``: what this call fetched, from which backend."""
    endpoints = list(ctx.stats.endpoints)
    return Source(
        endpoints=endpoints,
        backend=ctx.stats.backend if endpoints and ctx.stats.backend else "local",
        cached=ctx.stats.requests == 0 and ctx.stats.cache_hits > 0,
        derived=list(derived),
    )


def paginate(
    items: Sequence[T], *, offset: int, limit: int, total: int | None = None
) -> tuple[list[T], Page]:
    """Slice ``items`` and describe the slice as a :class:`Page`."""
    total = len(items) if total is None else total
    page_items = list(items[offset : offset + limit])
    returned = len(page_items)
    truncated = offset + returned < total
    return page_items, Page(
        total=total,
        returned=returned,
        offset=offset,
        limit=limit,
        truncated=truncated,
        next_offset=offset + returned if truncated else None,
        truncated_reason="limit" if truncated else None,
    )


def merge_notes(*groups: Sequence[str]) -> list[str]:
    out: list[str] = []
    for group in groups:
        out.extend(n for n in group if n not in out)
    return out


def compact_years(years: Sequence[int]) -> str | None:
    """``[1991, 1992, 1993, 2014]`` -> ``"1991-1993, 2014"``; empty -> ``None``."""
    ordered = sorted(set(years))
    if not ordered:
        return None
    runs: list[str] = []
    start = prev = ordered[0]
    for year in ordered[1:]:
        if year == prev + 1:
            prev = year
            continue
        runs.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = year
    runs.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(runs)


def parse_year_range(text: str | None, *, field: str = "years") -> tuple[int, int] | None:
    """``"2012"`` -> (2012, 2012); ``"2010-2015"`` / ``"2010:2015"`` -> (2010, 2015)."""
    from ameriflux_mcp.errors import ToolError

    if text is None or not text.strip():
        return None
    parts = [p.strip() for p in text.replace(":", "-").replace("–", "-").split("-")]
    try:
        if len(parts) == 1:
            year = int(parts[0])
            first, last = year, year
        elif len(parts) == 2:
            first, last = int(parts[0]), int(parts[1])
        else:
            raise ValueError
    except ValueError:
        raise ToolError(
            "invalid_argument",
            f"{field} must be a year (2012) or a range (2010-2015).",
            details={"field": field, "input": text},
        ) from None
    if not (1900 <= first <= last <= 2100):
        raise ToolError(
            "invalid_argument",
            f"{field} must run forwards between 1900 and 2100.",
            details={"field": field, "input": text},
        )
    return first, last


def range_years(text: str | None) -> list[int]:
    """``"1991-2012"`` (FLUXNET2015 tier ranges) -> every year in it; junk -> []."""
    if not text:
        return []
    try:
        bounds = parse_year_range(text)
    except Exception:
        return []
    return list(range(bounds[0], bounds[1] + 1)) if bounds else []
