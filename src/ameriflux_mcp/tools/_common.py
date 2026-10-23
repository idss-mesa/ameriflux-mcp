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
