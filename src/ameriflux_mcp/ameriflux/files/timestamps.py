"""Timestamps in AmeriFlux and FLUXNET files (RESEARCH.md section 6).

Stamps are digit strings whose length gives the precision: 12 ``YYYYMMDDHHMM`` (HH, HR
and the start/end of WW in some files), 8 ``YYYYMMDD`` (DD, WW), 6 ``YYYYMM`` (MM),
4 ``YYYY`` (YY). Time is local standard time without daylight saving; the offset to
UTC is the site's BADM ``GRP_UTC_OFFSET`` (possibly several, each from
``UTC_OFFSET_DATE_START``). ``TIMESTAMP_END`` of the last half hour of a year is the
next year's ``…01010000``: rows are assigned to years by their start.

Comparisons stay on digit strings: a window bound is padded to the stamp's length with
``0`` (start) or ``9`` (end), so ``end='2012'`` keeps every stamp of 2012.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta

from ameriflux_mcp.errors import ToolError

STEP_MINUTES: dict[str, int | None] = {
    "HH": 30,
    "HR": 60,
    "DD": 1440,
    "WW": 10080,
    "MM": None,
    "YY": None,
}
_NON_DIGITS = re.compile(r"[^0-9]")
#: 2012 | 2012-06 | 2012-06-01 | 2012-06-01T12[:00] | 201206 | 20120601 | 201206011200
_BOUND = re.compile(r"^\d{4}(?:-?\d{2}(?:-?\d{2}(?:[T ]?\d{2}(?::?\d{2})?)?)?)?$")


def parse(stamp: str) -> datetime | None:
    text = stamp.strip()
    try:
        if len(text) == 12:
            return datetime(
                int(text[:4]), int(text[4:6]), int(text[6:8]), int(text[8:10]), int(text[10:12])
            )
        if len(text) == 8:
            return datetime(int(text[:4]), int(text[4:6]), int(text[6:8]))
        if len(text) == 6:
            return datetime(int(text[:4]), int(text[4:6]), 1)
        if len(text) == 4:
            return datetime(int(text), 1, 1)
    except ValueError:
        return None
    return None


def iso(stamp: str) -> str | None:
    """``201101010030`` -> ``2011-01-01T00:30``; ``20110101`` -> ``2011-01-01``; …"""
    text = stamp.strip()
    if parse(text) is None:
        return None
    if len(text) == 12:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}T{text[8:10]}:{text[10:12]}"
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 6:
        return f"{text[:4]}-{text[4:6]}"
    return text


def step_minutes(start: str, end: str) -> int | None:
    """Length of one record from its start and end stamps (WW ends are inclusive days)."""
    a, b = parse(start), parse(end)
    if a is None or b is None or len(start.strip()) != len(end.strip()):
        return None
    if len(start.strip()) == 12:
        return int((b - a).total_seconds() // 60)
    if len(start.strip()) == 8:
        return ((b - a).days + 1) * 1440
    return None


def window_bound(text: str | None, *, field: str) -> str | None:
    """A user bound (``2012``, ``2012-06``, ``2012-06-01T12:00``, ``201206011200``) as digits."""
    if text is None or not text.strip():
        return None
    digits = _NON_DIGITS.sub("", text) if _BOUND.match(text.strip()) else ""
    parts = [digits[:4], digits[4:6] or "01", digits[6:8] or "01", digits[8:10] or "00"]
    parts.append(digits[10:12] or "00")
    valid = len(digits) in (4, 6, 8, 10, 12) and parse("".join(parts)) is not None
    if not valid:
        raise ToolError(
            "invalid_argument",
            f"{field} must be a date or time such as 2012, 2012-06, 2012-06-01 or "
            "2012-06-01T12:00.",
            details={"field": field, "input": text},
        )
    return digits


def padded(bound: str, length: int, *, end: bool) -> str:
    return (bound + ("9" if end else "0") * length)[:length]


def utc_offset_for(stamp: str, offsets: Sequence[tuple[str | None, float]]) -> float | None:
    """The offset in force at ``stamp`` from ``(date_start YYYYMMDD | None, hours)`` pairs."""
    chosen: float | None = None
    day = stamp[:8]
    for start, hours in sorted(offsets, key=lambda o: o[0] or ""):
        if start is None or start <= day:
            chosen = hours
    if chosen is None and offsets:
        chosen = sorted(offsets, key=lambda o: o[0] or "")[0][1]
    return chosen


def to_utc(stamp: str, offset_hours: float) -> str | None:
    """Local standard time -> UTC ISO (``2011-01-01T05:00Z``); only for 12-digit stamps."""
    moment = parse(stamp) if len(stamp.strip()) == 12 else None
    if moment is None:
        return None
    return (moment - timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%MZ")


__all__ = [
    "STEP_MINUTES",
    "iso",
    "padded",
    "parse",
    "step_minutes",
    "to_utc",
    "utc_offset_for",
    "window_bound",
]
