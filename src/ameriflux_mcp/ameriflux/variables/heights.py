"""Measurement heights and instruments of BASE variables (RESEARCH.md E30, E55).

AmeriFlux publishes one dated CSV (``BASE_MeasurementHeight_YYYYMMDD.csv``, about 2.3 MB,
40 000 rows) linked from ``ameriflux.lbl.gov/data/measurement-height/``; the file server
refuses directory listings, so the current file name is read from that page (one GET,
cached 24 h, within the site's 15 s crawl delay). Columns: Site_ID, Variable (with its
position qualifier, e.g. ``TA_1_2_1``), Start_Date, Height (m; negative is depth),
Instrument_Model, Instrument_Model2, Comment, BASE_Version. Start_Date is mostly empty
and some teams put a date in Comment instead, so both are passed on as written.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ameriflux_mcp.ameriflux.client import Fetched
from ameriflux_mcp.errors import AmeriFluxApiError
from ameriflux_mcp.models.upstream import to_float

if TYPE_CHECKING:
    from ameriflux_mcp.context import ToolContext

HEIGHTS_PAGE = "https://ameriflux.lbl.gov/data/measurement-height/"
CSV_LINK_RE = re.compile(
    r"https://ftp\.fluxdata\.org/\.ameriflux_downloads/measurement_height/"
    r"BASE_MeasurementHeight_(\d{8})\.csv"
)
COLUMNS = (
    "Site_ID",
    "Variable",
    "Start_Date",
    "Height",
    "Instrument_Model",
    "Instrument_Model2",
    "Comment",
    "BASE_Version",
)


@dataclass(frozen=True)
class HeightRow:
    variable: str
    height_m: float | None
    instrument: str | None
    instrument2: str | None
    start_date: str | None
    comment: str | None
    base_version: str | None


@dataclass(frozen=True)
class HeightsFile:
    url: str
    date: str
    raw: dict[str, list[list[Any]]]

    def site_rows(self, site_id: str) -> list[HeightRow]:
        return [HeightRow(*entry) for entry in self.raw.get(site_id, ())]


def parse_page(fetched: Fetched) -> dict[str, str]:
    """The newest CSV link on the measurement-height page."""
    matches = sorted({(m.group(1), m.group(0)) for m in CSV_LINK_RE.finditer(fetched.text)})
    if not matches:
        raise AmeriFluxApiError(
            fetched.status,
            "no BASE_MeasurementHeight_*.csv link on the page",
            fetched.endpoint,
            kind="drift",
            service="The AmeriFlux website",
            missing=["BASE_MeasurementHeight_*.csv"],
        )
    date, url = matches[-1]
    return {"url": url, "date": f"{date[:4]}-{date[4:6]}-{date[6:]}"}


def _blank(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def parse_csv(fetched: Fetched) -> dict[str, list[list[Any]]]:
    """``{site: [[variable, height, instrument, instrument2, start, comment, version]]}``."""
    reader = csv.reader(io.StringIO(fetched.body.decode("utf-8-sig", "replace")))
    header = next(reader, [])
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise AmeriFluxApiError(
            fetched.status,
            "measurement-height CSV columns changed",
            fetched.endpoint,
            kind="drift",
            service="The AmeriFlux file server",
            missing=missing,
        )
    at = {c: header.index(c) for c in COLUMNS}
    out: dict[str, list[list[Any]]] = {}
    for row in reader:
        if len(row) < len(header) or not row[at["Site_ID"]].strip():
            continue
        out.setdefault(row[at["Site_ID"]].strip(), []).append(
            [
                row[at["Variable"]].strip(),
                to_float(row[at["Height"]]),
                _blank(row[at["Instrument_Model"]]),
                _blank(row[at["Instrument_Model2"]]),
                _blank(row[at["Start_Date"]]),
                _blank(row[at["Comment"]]),
                _blank(row[at["BASE_Version"]]),
            ]
        )
    return out


async def heights_file(ctx: ToolContext) -> HeightsFile:
    """The current measurement-height file, indexed by site (cached 24 h)."""
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise RuntimeError("no upstream client")
    link = await ctx.client.fetch_url(
        HEIGHTS_PAGE, family="heights", parse=parse_page, stats=ctx.stats, accept="text/html"
    )
    raw = await ctx.client.fetch_url(
        link["url"], family="heights", parse=parse_csv, stats=ctx.stats, accept="text/csv"
    )
    return HeightsFile(url=link["url"], date=link["date"], raw=raw)


__all__ = ["HEIGHTS_PAGE", "HeightRow", "HeightsFile", "heights_file", "parse_csv", "parse_page"]
