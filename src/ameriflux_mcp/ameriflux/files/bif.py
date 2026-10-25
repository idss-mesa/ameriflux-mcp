"""BADM Interchange Format (BIF) files: xlsx in BASE-BADM downloads, CSV in FLUXNET zips.

Both forms are five columns (RESEARCH.md E33; ONEFlux README): ``SITE_ID``,
``GROUP_ID``, ``VARIABLE_GROUP``, ``VARIABLE``, ``DATAVALUE``. Rows sharing a GROUP_ID
form one entry (one team member, one UTC offset, one measurement period …).

BIF files carry personal data: team and DOI-contributor emails, postal and shipping
addresses, and the names of private land owners. These are withheld unless the caller
asks for contacts **and** the operator set ``privacy.allow_contact_emails`` (D19); any
value that looks like an email is withheld too.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ameriflux_mcp.ameriflux.files.xlsx import read_rows
from ameriflux_mcp.ameriflux.privacy import EMAIL_RE
from ameriflux_mcp.errors import ToolError

COLUMNS = ("SITE_ID", "GROUP_ID", "VARIABLE_GROUP", "VARIABLE", "DATAVALUE")
PERSONAL_SUFFIXES = ("_EMAIL", "_ADDRESS", "_PHONE")
PERSONAL_VARIABLES = frozenset({"LAND_OWNER", "SHIPPING_ADDRESS"})


@dataclass
class BifEntry:
    group: str
    group_id: str
    site_id: str
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class Bif:
    entries: list[BifEntry]
    withheld: int = 0

    @property
    def sites(self) -> list[str]:
        return sorted({e.site_id for e in self.entries if e.site_id})

    def groups(self, name: str) -> list[BifEntry]:
        return [e for e in self.entries if e.group == name]


@dataclass(frozen=True)
class UtcOffset:
    hours: float
    date_start: str | None
    comment: str | None
    site_id: str


def is_personal(variable: str, value: str) -> bool:
    upper = variable.upper()
    return (
        upper in PERSONAL_VARIABLES
        or upper.endswith(PERSONAL_SUFFIXES)
        or bool(EMAIL_RE.search(value))
    )


def rows_from_bytes(data: bytes, *, label: str, max_bytes: int) -> list[list[str]]:
    """Raw rows of a BIF file, xlsx (zip magic) or CSV."""
    if data[:4] == b"PK\x03\x04":
        return read_rows(data, label=label, max_bytes=max_bytes)
    text = data.decode("utf-8-sig", "replace")
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text)) if row]


def parse(rows: Sequence[Sequence[str]], *, label: str, allow_personal: bool = False) -> Bif:
    if not rows:
        raise ToolError("invalid_argument", f"{label} is empty.", details={"reason": "empty_file"})
    header = [h.strip().upper() for h in rows[0]]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise ToolError(
            "invalid_argument",
            f"{label} is not a BIF file (missing {', '.join(missing)}).",
            details={"reason": "not_bif", "columns": header[:10]},
        )
    at = {c: header.index(c) for c in COLUMNS}
    entries: dict[tuple[str, str, str], BifEntry] = {}
    withheld = 0
    for row in rows[1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        site, gid, group, variable, value = (cells[at[c]].strip() for c in COLUMNS)
        if not group or not variable:
            continue
        key = (site, group, gid)
        entry = entries.setdefault(key, BifEntry(group=group, group_id=gid, site_id=site))
        if not allow_personal and is_personal(variable, value):
            withheld += 1
            continue
        entry.values[variable] = value
    return Bif(entries=[e for e in entries.values() if e.values], withheld=withheld)


def utc_offsets(bif: Bif) -> list[UtcOffset]:
    out: list[UtcOffset] = []
    for entry in bif.groups("GRP_UTC_OFFSET"):
        try:
            hours = float(entry.values.get("UTC_OFFSET", ""))
        except ValueError:
            continue
        start = "".join(ch for ch in entry.values.get("UTC_OFFSET_DATE_START", "") if ch.isdigit())
        out.append(
            UtcOffset(
                hours=hours,
                date_start=start[:8] or None,
                comment=entry.values.get("UTC_OFFSET_COMMENT") or None,
                site_id=entry.site_id,
            )
        )
    return sorted(out, key=lambda o: (o.site_id, o.date_start or ""))


def first_value(entries: Iterable[BifEntry], variable: str) -> str | None:
    for entry in entries:
        if entry.values.get(variable):
            return entry.values[variable]
    return None


__all__ = [
    "COLUMNS",
    "PERSONAL_SUFFIXES",
    "PERSONAL_VARIABLES",
    "Bif",
    "BifEntry",
    "UtcOffset",
    "first_value",
    "is_personal",
    "parse",
    "rows_from_bytes",
    "utc_offsets",
]
