"""Per-variable, per-year coverage of BASE data: amerifluxr's dated snapshot (RESEARCH.md E31).

The AmeriFlux API has no coverage endpoint (its ``variable_availability`` is a POST and is
never called). amerifluxr publishes a network-wide CSV on GitHub,
``AMF_AA-Flx_BASE_VARIABLE-AVAILABILITY_LATEST.csv`` (6.5 MB): a ``create_date:`` line,
then SITE_ID, VARIABLE, BASENAME, GAP_FILLED and one column per year (Y1990 …) holding
the fraction of that year with data. It lags the live BASE releases, so every use
carries the snapshot date. Loaded lazily, cached 7 days, kept compact (years with no
data are dropped).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ameriflux_mcp.ameriflux.client import Fetched
from ameriflux_mcp.errors import AmeriFluxApiError
from ameriflux_mcp.models.upstream import to_float

if TYPE_CHECKING:
    from ameriflux_mcp.context import ToolContext

COVERAGE_URL = (
    "https://raw.githubusercontent.com/chuhousen/amerifluxr/master/data-summary/"
    "AMF_AA-Flx_BASE_VARIABLE-AVAILABILITY_LATEST.csv"
)
COLUMNS = ("SITE_ID", "VARIABLE", "BASENAME", "GAP_FILLED")
#: Largest snapshot read (6.5 MB on 2026-10-24).
MAX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class CoverageRow:
    variable: str
    basename: str
    gap_filled: bool
    #: year -> fraction of the year with data (0 < f <= 1); years without data are absent.
    years: dict[int, float]


@dataclass(frozen=True)
class Coverage:
    created: str | None
    raw: dict[str, list[list[Any]]]

    def site_rows(self, site_id: str) -> list[CoverageRow]:
        return [
            CoverageRow(v, b, bool(g), {int(y): f for y, f in years.items()})
            for v, b, g, years in self.raw.get(site_id, ())
        ]


def parse_csv(fetched: Fetched) -> dict[str, Any]:
    text = fetched.body.decode("utf-8-sig", "replace")
    created: str | None = None
    if text.startswith("create_date:"):
        first, _, text = text.partition("\n")
        created = first.split(":", 1)[1].strip().strip(",") or None
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    missing = [c for c in COLUMNS if c not in header]
    year_cols = [(i, int(h[1:])) for i, h in enumerate(header) if h[:1] == "Y" and h[1:].isdigit()]
    if missing or not year_cols:
        raise AmeriFluxApiError(
            fetched.status,
            "coverage snapshot columns changed",
            fetched.endpoint,
            kind="drift",
            service="The amerifluxr snapshot repository",
            missing=missing or ["Y<year>"],
        )
    at = {c: header.index(c) for c in COLUMNS}
    sites: dict[str, list[list[Any]]] = {}
    for row in reader:
        if len(row) < len(header):
            continue
        years: dict[str, float] = {}
        for i, year in year_cols:
            value = to_float(row[i])
            if value and value > 0:
                years[str(year)] = round(value, 3)
        sites.setdefault(row[at["SITE_ID"]], []).append(
            [
                row[at["VARIABLE"]],
                row[at["BASENAME"]],
                row[at["GAP_FILLED"]].strip().upper() == "TRUE",
                years,
            ]
        )
    return {"created": created, "sites": sites}


async def coverage(ctx: ToolContext) -> Coverage:
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise RuntimeError("no upstream client")
    data = await ctx.client.fetch_url(
        COVERAGE_URL,
        family="coverage",
        parse=parse_csv,
        stats=ctx.stats,
        accept="text/csv",
        max_bytes=MAX_BYTES,
    )
    return Coverage(created=data.get("created"), raw=data["sites"])


__all__ = ["COVERAGE_URL", "Coverage", "CoverageRow", "coverage", "parse_csv"]
