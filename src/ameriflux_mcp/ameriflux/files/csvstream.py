"""Stream one AmeriFlux or FLUXNET CSV: summaries and row windows within a budget (D36).

* Leading ``#`` lines (BASE has ``# Site: US-CRT`` and ``# Version: 2-5``, padded with
  commas) are kept as header metadata; FLUXNET files start with the header row.
* Time series need ``TIMESTAMP_START`` (with ``TIMESTAMP_END``) or ``TIMESTAMP``; auxiliary
  tables (FLUXNET2015 AUXMETEO/AUXNEE) are read without that requirement.
* Columns are selected by name, never by position (column order is not guaranteed).
* ``-9999`` (and ``-9999.0``, ``-9999.9``) and empty cells are missing values.
* Values outside a plausible range are counted (``outOfRange``), never dropped.
* A QC rule nulls values whose ``<NAME>_QC`` companion fails it: ``max`` for the
  categorical flags at HH (0 measured … 3 poor), ``min_fraction`` for the 0–1 fractions
  at DD and coarser.
* Files are time-ordered, so a scan stops after ``end``; it also stops after
  ``max_bytes`` or ``time_budget_s`` and reports ``truncatedReason='budget'``.
"""

from __future__ import annotations

import csv
import difflib
import io
import re
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import IO, Literal

from ameriflux_mcp.ameriflux.files.timestamps import padded, step_minutes
from ameriflux_mcp.errors import ToolError

MISSING_RE = re.compile(r"^-9999(?:\.0*|\.9+)?$")
TIMESTAMP_COLUMNS = ("TIMESTAMP_START", "TIMESTAMP_END", "TIMESTAMP")
MAX_COLUMNS = 400
CHECK_EVERY = 2000
Value = float | str | None


@dataclass(frozen=True)
class QcRule:
    kind: Literal["max", "min_fraction"]
    threshold: float

    def passes(self, qc: float) -> bool:
        return qc <= self.threshold if self.kind == "max" else qc >= self.threshold


@dataclass
class ColumnStats:
    name: str
    count: int = 0
    missing: int = 0
    minimum: float | None = None
    maximum: float | None = None
    total: float = 0.0
    out_of_range: int = 0
    qc_filtered: int = 0
    text: int = 0
    text_values: list[str] = field(default_factory=list)

    @property
    def mean(self) -> float | None:
        return self.total / self.count if self.count else None

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        if self.minimum is None or value < self.minimum:
            self.minimum = value
        if self.maximum is None or value > self.maximum:
            self.maximum = value


@dataclass
class ScanResult:
    header_lines: list[str]
    columns: list[str]
    selected: list[str]
    timestamp_columns: list[str]
    stats: dict[str, ColumnStats]
    rows: list[list[Value]] = field(default_factory=list)
    rows_scanned: int = 0
    rows_matched: int = 0
    first: str | None = None
    last: str | None = None
    step_minutes: int | None = None
    truncated_reason: Literal["budget"] | None = None
    more_rows: bool = False
    stopped_at_end: bool = False
    bytes_read: int = 0
    qc_columns: dict[str, str] = field(default_factory=dict)


class _Counter(io.RawIOBase):
    def __init__(self, raw: IO[bytes]) -> None:
        self._raw = raw
        self.count = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        data = self._raw.read(len(buffer))
        self.count += len(data)
        buffer[: len(data)] = data
        return len(data)


def _number(text: str) -> float | str | None:
    """A float, ``None`` (missing) or the text itself (non-numeric)."""
    if not text or MISSING_RE.match(text):
        return None
    try:
        return float(text)
    except ValueError:
        return text


def _pick(columns: Sequence[str], wanted: Sequence[str]) -> list[str]:
    by_fold = {c.casefold(): c for c in columns}
    out: list[str] = []
    unknown: list[str] = []
    for name in wanted:
        match = by_fold.get(name.strip().casefold())
        if match is None:
            unknown.append(name)
        elif match not in out:
            out.append(match)
    if unknown:
        raise ToolError(
            "invalid_argument",
            f"Not in this file: {', '.join(unknown[:10])}.",
            details={
                "reason": "unknown_columns",
                "unknown": unknown[:20],
                "didYouMean": {
                    u: difflib.get_close_matches(u.upper(), list(columns), n=3, cutoff=0.6)
                    for u in unknown[:5]
                },
            },
        )
    return out


@dataclass(frozen=True)
class Header:
    lines: list[str]
    columns: list[str]

    @property
    def timestamps(self) -> list[str]:
        return [c for c in TIMESTAMP_COLUMNS if c in self.columns]

    @property
    def values(self) -> list[str]:
        return [c for c in self.columns if c not in TIMESTAMP_COLUMNS]


def _open(binary: IO[bytes]) -> tuple[_Counter, Header, Iterator[list[str]]]:
    counter = _Counter(binary)
    text = io.TextIOWrapper(
        io.BufferedReader(counter, buffer_size=1024 * 1024),
        encoding="utf-8",
        errors="replace",
        newline="",
    )
    header_lines: list[str] = []
    first_line = ""
    for line in text:
        stripped = line.lstrip("\ufeff")
        if stripped.startswith("#"):
            header_lines.append(stripped.strip().rstrip(",").strip())
            continue
        first_line = stripped
        break
    if not first_line.strip():
        raise ToolError(
            "invalid_argument", "The file has no header row.", details={"reason": "empty_file"}
        )
    reader: Iterator[list[str]] = csv.reader(_chain(first_line, text))
    columns = [h.strip() for h in next(reader)]
    return counter, Header(header_lines, columns), reader


def header(binary: IO[bytes]) -> Header:
    """The ``#`` lines and the column names, without reading the data."""
    return _open(binary)[1]


def scan(
    binary: IO[bytes],
    *,
    columns: Sequence[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    want_rows: bool = False,
    offset: int = 0,
    max_rows: int = 100,
    qc: QcRule | None = None,
    ranges: Mapping[str, tuple[float, float]] | None = None,
    require_timestamps: bool = True,
    max_bytes: int = 256 * 1024 * 1024,
    time_budget_s: float = 20.0,
    clock: Callable[[], float] = time.monotonic,
) -> ScanResult:
    counter, head, reader = _open(binary)
    header_lines, header = head.lines, head.columns
    ts_cols = [c for c in TIMESTAMP_COLUMNS if c in header]
    if require_timestamps and not ts_cols:
        raise ToolError(
            "invalid_argument",
            "No TIMESTAMP_START or TIMESTAMP column: this is not an AmeriFlux or FLUXNET time "
            "series.",
            details={"reason": "no_timestamps", "columns": header[:20]},
        )
    if (start or end) and not ts_cols:
        raise ToolError(
            "invalid_argument",
            "start and end need a time series; this table has no timestamps.",
            details={"reason": "no_timestamps"},
        )
    values = [c for c in header if c not in ts_cols]
    selected = _pick(header, columns) if columns else values[:MAX_COLUMNS]
    selected = [c for c in selected if c not in ts_cols]
    index = {c: i for i, c in enumerate(header)}
    key_col = (
        "TIMESTAMP_START" if "TIMESTAMP_START" in index else ("TIMESTAMP" if ts_cols else None)
    )
    key_i = index[key_col] if key_col else None
    end_i = index.get("TIMESTAMP_END")
    sel = [(c, index[c]) for c in selected]
    qc_index = {c: index[f"{c}_QC"] for c in selected if qc is not None and f"{c}_QC" in index}
    limits = dict(ranges or {})
    stats = {c: ColumnStats(c) for c in selected}
    result = ScanResult(
        header_lines=header_lines,
        columns=header,
        selected=selected,
        timestamp_columns=ts_cols,
        stats=stats,
        qc_columns={c: f"{c}_QC" for c in qc_index},
    )
    started = clock()
    width = len(header)
    start_key = end_key = None
    for row in reader:
        result.rows_scanned += 1
        if result.rows_scanned % CHECK_EVERY == 0 and (
            counter.count > max_bytes or clock() - started > time_budget_s
        ):
            result.truncated_reason = "budget"
            break
        if len(row) < width:
            row = row + [""] * (width - len(row))
        key = row[key_i].strip() if key_i is not None else None
        if key:
            if start and start_key is None:
                start_key = padded(start, len(key), end=False)
            if end and end_key is None:
                end_key = padded(end, len(key), end=True)
            if start_key is not None and key < start_key:
                continue
            if end_key is not None and key > end_key:
                result.stopped_at_end = True
                break
        result.rows_matched += 1
        if key:
            if result.first is None:
                result.first = key
                if end_i is not None:
                    result.step_minutes = step_minutes(key, row[end_i].strip())
            result.last = key
        out: list[Value] | None = None
        if want_rows and result.rows_matched > offset:
            if len(result.rows) >= max_rows:
                result.more_rows = True
                break
            out = [row[index[c]].strip() for c in ts_cols]
        for name, i in sel:
            value = _number(row[i].strip())
            column = stats[name]
            if value is None:
                column.missing += 1
            elif isinstance(value, str):
                column.text += 1
                if len(column.text_values) < 5 and value not in column.text_values:
                    column.text_values.append(value[:80])
            else:
                qi = qc_index.get(name)
                if qi is not None and qc is not None:
                    flag = _number(row[qi].strip())
                    if isinstance(flag, float) and not qc.passes(flag):
                        column.qc_filtered += 1
                        value = None
                if value is not None:
                    column.add(value)
                    bounds = limits.get(name)
                    if bounds and not bounds[0] <= value <= bounds[1]:
                        column.out_of_range += 1
            if out is not None:
                out.append(value)
        if out is not None:
            result.rows.append(out)
    result.bytes_read = counter.count
    return result


def _chain(first: str, rest: Iterator[str]) -> Iterator[str]:
    yield first
    yield from rest


__all__ = ["MISSING_RE", "ColumnStats", "Header", "QcRule", "ScanResult", "header", "scan"]
