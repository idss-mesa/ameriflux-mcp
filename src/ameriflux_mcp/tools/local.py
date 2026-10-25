"""Local files: ``amf_list_files``, ``amf_preview_data``, ``amf_read_bif`` (build step 6).

stdio only. They read files the user already has, in the download directory or a
configured ``local.roots`` folder, and never touch the network: units and plausible
ranges come from the bundled dictionaries. Archives are read in place through
:class:`~ameriflux_mcp.ameriflux.files.zipsafe.SafeZip`; scans run in a worker thread
under the byte and time budgets of ``limits``.
"""

from __future__ import annotations

import asyncio
import zipfile
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, ClassVar, Literal, TypeVar, cast

from pydantic import Field

from ameriflux_mcp.ameriflux.files import bif as bifmod
from ameriflux_mcp.ameriflux.files import csvstream, timestamps
from ameriflux_mcp.ameriflux.files.filenames import FileName, classify
from ameriflux_mcp.ameriflux.files.inventory import (
    Found,
    classified_members,
    pick_bif,
    pick_table,
    version_key,
    walk,
)
from ameriflux_mcp.ameriflux.files.paths import (
    MEMBER_SEPARATOR,
    LocalPath,
    resolve_dir,
    resolve_file,
    roots,
)
from ameriflux_mcp.ameriflux.files.zipsafe import SafeZip
from ameriflux_mcp.ameriflux.privacy import CONTACTS_WITHHELD_NOTE, contacts_allowed
from ameriflux_mcp.ameriflux.products import normalize_product
from ameriflux_mcp.ameriflux.variables.dictionaries import fluxnet_dictionary, fp_snapshot
from ameriflux_mcp.ameriflux.variables.grammar import fluxnet_template, parse
from ameriflux_mcp.config import Config
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Page, ToolResultBase
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import merge_notes, paginate, source

T = TypeVar("T")
LOCAL = ("stdio",)
RANGE_BUFFER = 0.05
MAX_SUMMARY_COLUMNS = 80
DEFAULT_ROW_COLUMNS = 10


def _iso_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _years(name: FileName) -> str | None:
    if name.first_year is None:
        return None
    return f"{name.first_year}-{name.last_year}"


def _bad_zip(label: str) -> ToolError:
    return ToolError(
        "invalid_argument",
        f"{label} is corrupt (a zip member failed its checksum).",
        details={"reason": "bad_zip"},
    )


async def _in_thread(fn: Callable[[], T]) -> T:
    try:
        return await asyncio.to_thread(fn)
    except zipfile.BadZipFile:
        raise _bad_zip("The archive") from None


# ---------------------------------------------------------------------- amf_list_files


class ListFilesIn(AmfInput):
    path: str | None = Field(
        None,
        max_length=1000,
        description="A folder or archive inside the download directory or a local root; "
        "default: every root.",
    )
    family: list[Literal["base", "bif", "fluxnet", "fluxnet2015", "fluxnet_ch4"]] | None = Field(
        None, description="Only these families."
    )
    site: str | None = Field(None, max_length=20, description="Only this site ID (any case).")
    include_members: bool = Field(True, description="Classify the members of each archive.")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class MemberEntry(AmfOutput):
    name: str
    size: int
    family: str | None = None
    kind: str | None = None
    resolution: str | None = None
    years: str | None = None
    refused: str | None = Field(None, description="Why the member cannot be read, if it cannot.")


class FileEntry(AmfOutput):
    path: str = Field(description="Relative to its root; pass to amf_preview_data(file=...).")
    root: str
    size: int
    modified: str
    family: str
    kind: str = Field(
        description="data, era, bifvarinfo, bif, aux_table (FLUXNET2015 AUXMETEO/AUXNEE), "
        "archive, readme or license."
    )
    product: str | None = None
    site_id: str | None = None
    resolution: str | None = Field(
        None, description="HH, HR, DD, WW, MM or YY (ONEFlux v1.3 HH may be hourly)."
    )
    years: str | None = None
    version: str | None = None
    variant: str | None = None
    members: list[MemberEntry] | None = None
    members_total: int | None = None
    note: str | None = None


class ListFacets(AmfOutput):
    family: dict[str, int]
    site: dict[str, int]


class ListFilesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "files"
    budget_elide_fields: ClassVar[tuple[str, ...]] = ("members",)
    budget_elide_flag: ClassVar[str | None] = "members_elided"
    roots: list[str]
    files: list[FileEntry]
    facets: ListFacets
    unrecognized: int = Field(description="Files skipped because their names are not ours.")
    members_elided: bool | None = None
    page: Page


MAX_MEMBERS_SHOWN = 40


def _member_entries(found: Found, config: Config) -> tuple[list[MemberEntry], int, str | None]:
    try:
        with SafeZip(
            found.path, max_member_bytes=config.limits.zip_member_max_bytes, label=found.name.name
        ) as archive:
            entries = [
                MemberEntry(
                    name=member.name,
                    size=member.size,
                    family=name.family if name else None,
                    kind=name.kind if name else None,
                    resolution=name.resolution if name else None,
                    years=_years(name) if name else None,
                    refused=member.refused,
                )
                for member, name in classified_members(archive)
            ]
    except ToolError as exc:
        return [], 0, exc.message
    return entries[:MAX_MEMBERS_SHOWN], len(entries), None


@register_tool(
    "amf_list_files",
    title="List local AmeriFlux and FLUXNET files",
    description=(
        "Find the AmeriFlux and FLUXNET files already on this computer, in the download "
        "directory and configured local roots: BASE and BASE-BADM zips, BIF files, AmeriFlux "
        "FLUXNET (ONEFlux) and FLUXNET2015 archives, with each archive's members classified by "
        "kind (data, ERA, BIFVARINFO, BIF, aux tables), site, resolution, years and version. "
        "Unsafe members are flagged. stdio only. Next: call amf_preview_data(file=...) on one."
    ),
    input_model=ListFilesIn,
    output_model=ListFilesResult,
    surface="local",
    endpoints=[],
    transports=LOCAL,
    open_world=False,
)
async def amf_list_files(args: ListFilesIn, ctx: ToolContext) -> ListFilesResult:
    config = ctx.config
    notes: list[str] = []
    single: Found | None = None
    if args.path and Path(args.path.split(MEMBER_SEPARATOR, 1)[0]).suffix.lower() == ".zip":
        local = resolve_file(args.path, config)
        name = classify(local.path.name)
        if name is None:
            raise ToolError(
                "invalid_argument",
                f"{local.path.name} is not an AmeriFlux or FLUXNET archive name.",
                details={"reason": "unrecognized_name"},
            )
        stat = local.path.stat()
        single = Found(local.path, local.root, name, stat.st_size, stat.st_mtime)
        found, unrecognized = [single], 0
    else:
        dirs = resolve_dir(args.path, config)
        if not dirs:
            notes.append(
                "No local folder exists yet: the download directory is created by the first "
                "download, and local.roots adds folders such as FLUXNET2015 zips from fluxnet.org."
            )
        result = await asyncio.to_thread(walk, dirs)
        found, unrecognized = result.found, result.unrecognized
        if result.capped:
            notes.append(f"Stopped after {result.examined - 1} files; narrow path to see the rest.")
    if args.family:
        found = [f for f in found if f.name.family in args.family]
    if args.site:
        wanted = args.site.strip().casefold()
        found = [f for f in found if (f.name.site_id or "").casefold() == wanted]
    found.sort(key=lambda f: (f.relative, str(f.root)))
    page_items, page = paginate(found, offset=args.offset, limit=args.limit)
    files: list[FileEntry] = []
    for f in page_items:
        entry = FileEntry(
            path=f.relative,
            root=str(f.root),
            size=f.size,
            modified=_iso_mtime(f.mtime),
            family=f.name.family,
            kind=f.name.kind,
            product=f.name.product or None,
            site_id=f.name.site_id,
            resolution=f.name.resolution,
            years=_years(f.name),
            version=f.name.version,
            variant=f.name.variant,
        )
        if f.name.family == "fluxnet_ch4":
            entry.note = "FLUXNET-CH4 files are recognized; reading them arrives in v0.2."
        if f.name.is_archive and args.include_members:
            members, total, problem = await asyncio.to_thread(_member_entries, f, config)
            entry.members, entry.members_total = members, total
            if problem:
                entry.note = problem
            elif total > len(members):
                entry.note = f"{total} members; the first {len(members)} are shown."
        files.append(entry)
    facets = ListFacets(
        family=dict(Counter(f.name.family for f in found).most_common()),
        site=dict(Counter(f.name.site_id or "?" for f in found).most_common(30)),
    )
    steps: list[str] = []
    first_data = next((f for f in files if f.kind in ("archive", "data")), None)
    if first_data:
        steps.append(f"amf_preview_data(file='{first_data.path}') for a summary of its data")
    first_bif = next((f for f in files if f.kind == "bif" or f.family == "base"), None)
    if first_bif:
        steps.append(f"amf_read_bif(file='{first_bif.path}') for its site metadata")
    if page.next_offset is not None:
        steps.append(f"amf_list_files(..., offset={page.next_offset}) for the next page")
    if not found:
        notes.append("No AmeriFlux or FLUXNET files found under the local roots.")
    return ListFilesResult(
        roots=[str(r) for r in roots(config)],
        files=files,
        facets=facets,
        unrecognized=unrecognized,
        page=page,
        notes=notes,
        next_steps=steps,
        source=source(ctx),
    )


# ---------------------------------------------------------------------- shared: targets


@dataclass(frozen=True)
class Target:
    local: LocalPath
    #: The table (or BIF) being read: the file itself or the chosen member.
    name: FileName
    member: str | None
    container: FileName | None

    @property
    def display(self) -> str:
        return self.local.relative + (f"{MEMBER_SEPARATOR}{self.member}" if self.member else "")


def _open_stream(target: Target, config: Config) -> tuple[IO[bytes], SafeZip | None]:
    if target.member is None:
        return target.local.path.open("rb"), None
    archive = SafeZip(
        target.local.path,
        max_member_bytes=config.limits.zip_member_max_bytes,
        label=target.local.path.name,
    )
    try:
        return cast(IO[bytes], archive.open(target.member)), archive
    except BaseException:
        archive.close()
        raise


def _with_stream(target: Target, config: Config, fn: Callable[[IO[bytes]], T]) -> T:
    stream, archive = _open_stream(target, config)
    try:
        return fn(stream)
    finally:
        stream.close()
        if archive is not None:
            archive.close()


def _resolve_member(
    local: LocalPath, config: Config, pick: Callable[[SafeZip, FileName], str]
) -> Target:
    container = classify(local.path.name)
    if container is None or not container.is_archive:
        if local.member:
            raise ToolError(
                "invalid_argument",
                "::member applies to zip archives only.",
                details={"reason": "not_an_archive"},
            )
        name = classify(local.path.name)
        if name is None:
            raise ToolError(
                "invalid_argument",
                f"{local.path.name} is not an AmeriFlux or FLUXNET file name.",
                details={"reason": "unrecognized_name"},
                hint="Files keep the names AmeriFlux and FLUXNET give them; see amf_list_files.",
            )
        return Target(local, name, None, None)
    with SafeZip(
        local.path, max_member_bytes=config.limits.zip_member_max_bytes, label=local.path.name
    ) as archive:
        member_name = (
            archive.member(local.member).name if local.member else pick(archive, container)
        )
    name = classify(member_name)
    if name is None:
        raise ToolError(
            "invalid_argument",
            f"{member_name} is not an AmeriFlux or FLUXNET file name.",
            details={"reason": "unrecognized_name"},
        )
    return Target(local, name, member_name, container)


def _find_by_site(site: str, product: str, config: Config) -> Found:
    families = {
        "BASE-BADM": ("base",),
        "FLUXNET": ("fluxnet",),
        "FLUXNET2015": ("fluxnet2015",),
        "BIF": ("bif", "base", "fluxnet"),
    }[product]
    wanted = site.strip().casefold()
    result = walk(resolve_dir(None, config))
    candidates = [
        f
        for f in result.found
        if f.name.family in families
        and (f.name.site_id or "").casefold() == wanted
        and (f.name.kind in ("archive", "data") or (product == "BIF" and f.name.kind == "bif"))
    ]
    if not candidates:
        raise ToolError(
            "not_found",
            f"No local {product} file for {site}.",
            details={"reason": "no_local_file", "site": site, "product": product},
            hint="List what is here with amf_list_files; downloads arrive with amf_download_data.",
        )
    return max(candidates, key=lambda f: (version_key(f.name), f.name.kind == "archive", f.mtime))


# ---------------------------------------------------------------------- amf_preview_data


class PreviewIn(AmfInput):
    file: str | None = Field(
        None,
        max_length=1000,
        description="A file or 'archive.zip::member.csv', relative to a local root (see "
        "amf_list_files). Or give site and product instead.",
    )
    site: str | None = Field(None, max_length=20, description="Newest local file of this site.")
    product: str | None = Field(
        None, description="With site: BASE-BADM (default), FLUXNET or FLUXNET2015."
    )
    resolution: Literal["HH", "HR", "DD", "WW", "MM", "YY"] | None = Field(
        None, description="Member of an archive to read (default HH; HR sites match HH)."
    )
    columns: list[str] | None = Field(
        None, max_length=60, description="Columns by name (default: up to 80 in summaries)."
    )
    start: str | None = Field(None, description="First time, e.g. 2012, 2012-06, 2012-06-01T12:00.")
    end: str | None = Field(
        None, description="Last time (inclusive): end='2012' keeps all of 2012."
    )
    mode: Literal["summary", "rows"] = Field(
        "summary", description="summary: per-column statistics; rows: a window of rows."
    )
    max_rows: int = Field(100, ge=1, le=5000, description="Rows per page (capped by the server).")
    offset: int = Field(0, ge=0, description="Rows to skip within the time window.")
    qc_max: int | None = Field(
        None, ge=0, le=3, description="HH/HR FLUXNET: keep values whose _QC flag is at most this."
    )
    qc_min_fraction: float | None = Field(
        None,
        ge=0,
        le=1,
        description="DD and coarser FLUXNET: keep values whose _QC fraction is at least this.",
    )
    to_utc: bool = Field(False, description="Add UTC timestamps (offset from the site's BIF).")
    view: Literal["full", "subset"] = Field(
        "full", description="subset: only FLUXNET2015 SUBSET variables (AmeriFlux FLUXNET files)."
    )


class TimeRange(AmfOutput):
    first: str | None = None
    last: str | None = None


class UtcOffsetOut(AmfOutput):
    hours: float
    date_start: str | None = None
    site_id: str | None = None
    comment: str | None = None


class FileInfo(AmfOutput):
    path: str
    member: str | None = None
    family: str
    kind: str
    product: str | None = None
    site_id: str | None = None
    resolution: str | None = None
    version: str | None = None
    step_minutes: int | None = Field(None, description="From the timestamps: 30, 60, 1440 …")
    time_range: TimeRange | None = Field(None, description="Of the rows scanned in the window.")
    header_lines: list[str] = Field(default_factory=list, description="Leading # lines.")
    columns_total: int
    utc_offsets: list[UtcOffsetOut] = Field(
        default_factory=list, description="Local standard time = UTC + hours (site BIF)."
    )


class ColumnSummary(AmfOutput):
    name: str
    units: str | None = None
    count: int = Field(description="Values present (after the QC filter).")
    missing: int = Field(description="-9999 or empty.")
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    out_of_range: int | None = Field(
        None, description="Outside the FP Standard range ±5% (counted, never dropped)."
    )
    qc_filtered: int | None = None
    text_values: list[str] | None = Field(None, description="Non-numeric values seen (aux tables).")


class ScanInfo(AmfOutput):
    rows_scanned: int
    rows_matched: int
    bytes_read: int
    truncated_reason: Literal["budget"] | None = None
    stats_scope: Literal["window", "rows"] = Field(
        description="window: statistics cover every matching row scanned; rows: only the rows "
        "returned."
    )


class PreviewResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "rows"
    file_info: FileInfo
    columns: list[ColumnSummary]
    row_columns: list[str] | None = None
    rows: list[list[float | str | None]] | None = None
    scan: ScanInfo
    page: Page | None = None


def _ranges(
    target: Target, selected: Sequence[str]
) -> tuple[dict[str, tuple[float, float]], dict[str, str | None]]:
    """Plausible ranges (FP Standard ±5%) and units per column, from the bundled lists."""
    fp = fp_snapshot().by_name()
    names = frozenset(fp)
    fluxnet = fluxnet_dictionary()
    res = target.name.resolution or "HH"
    dict_res = "HH" if res in ("HH", "HR") else res
    ranges: dict[str, tuple[float, float]] = {}
    units: dict[str, str | None] = {}
    for column in selected:
        parsed = parse(column, names)
        base = fp.get(parsed.basename or "")
        entry = fluxnet.get(fluxnet_template(column)) or fluxnet.get(column)
        if target.name.family == "base":
            unit = None if base is None else ("nondimensional" if parsed.is_qc else base.units)
        else:
            unit = (
                entry.units.get(dict_res)
                if entry
                else (base.units if base and parsed.grammar == "base" else None)
            )
        units[column] = unit
        if base is None or parsed.is_qc or (base.min is None and base.max is None):
            continue
        if target.name.family != "base" and (dict_res != "HH" or unit != base.units):
            continue
        lo = base.min if base.min is not None else float("-inf")
        hi = base.max if base.max is not None else float("inf")
        span = (
            (hi - lo)
            if base.min is not None and base.max is not None
            else abs(lo if base.min is not None else hi)
        )
        ranges[column] = (lo - RANGE_BUFFER * span, hi + RANGE_BUFFER * span)
    return ranges, units


def _bif_bytes(target: Target, config: Config) -> tuple[bytes, str] | None:
    """The site's BIF: from the same archive, else the newest AMF_<site>_BIF_*.xlsx beside it."""
    max_bytes = config.limits.zip_member_max_bytes
    if target.container is not None:
        with SafeZip(
            target.local.path, max_member_bytes=max_bytes, label=target.local.path.name
        ) as archive:
            member = pick_bif(archive)
            if member is not None:
                return archive.read(member.name), f"{target.local.relative}::{member.name}"
    site = (target.name.site_id or "").casefold()
    siblings = []
    for path in target.local.path.parent.iterdir():
        name = classify(path.name)
        if (
            name
            and name.kind == "bif"
            and name.family == "bif"
            and (name.site_id or "").casefold() == site
        ):
            siblings.append((name.date or "", path))
    if siblings and not any(p.is_symlink() for _, p in siblings):
        path = max(siblings)[1]
        if path.stat().st_size <= max_bytes:
            return path.read_bytes(), path.relative_to(target.local.root).as_posix()
    return None


@register_tool(
    "amf_preview_data",
    title="Preview a local AmeriFlux or FLUXNET data file",
    description=(
        "Summarize or page through a local BASE, AmeriFlux FLUXNET or FLUXNET2015 CSV, in place "
        "or inside its zip: time step and range, per-column count, missing (-9999), min, max, "
        "mean and out-of-range counts, units per resolution, a time window, a QC filter, UTC "
        "timestamps from the site's BIF, a SUBSET column view, and aux tables. Stops within a "
        "byte and time budget. stdio only. Next: call amf_describe_variables on columns to "
        "decode."
    ),
    input_model=PreviewIn,
    output_model=PreviewResult,
    surface="local",
    endpoints=[],
    transports=LOCAL,
    open_world=False,
)
async def amf_preview_data(args: PreviewIn, ctx: ToolContext) -> PreviewResult:
    config = ctx.config
    limits = config.limits
    notes: list[str] = []
    start = timestamps.window_bound(args.start, field="start")
    end = timestamps.window_bound(args.end, field="end")
    if (
        start
        and end
        and timestamps.padded(start, 12, end=False) > timestamps.padded(end, 12, end=True)
    ):
        raise ToolError(
            "invalid_argument",
            "start is after end.",
            details={"start": args.start, "end": args.end},
        )
    if args.qc_max is not None and args.qc_min_fraction is not None:
        raise ToolError(
            "invalid_argument",
            "Use qc_max (HH/HR flags) or qc_min_fraction (DD and coarser), not both.",
            details={"reason": "qc_conflict"},
        )

    def pick(archive: SafeZip, container: FileName) -> str:
        return pick_table(archive, container, args.resolution).name

    if args.file:
        local = resolve_file(args.file, config)
    elif args.site:
        product = normalize_product(args.product or "BASE-BADM")
        if product not in ("BASE-BADM", "FLUXNET", "FLUXNET2015"):
            raise ToolError(
                "invalid_argument",
                "product must be BASE-BADM, FLUXNET or FLUXNET2015 here.",
                details={"reason": "product", "input": args.product},
            )
        found = await asyncio.to_thread(_find_by_site, args.site, product, config)
        local = LocalPath(found.path, found.root)
        notes.append(
            f"Reading the newest local {product} file of {found.name.site_id}: {found.relative}."
        )
    else:
        raise ToolError(
            "invalid_argument",
            "Give file, or site (with product).",
            details={"reason": "no_target"},
        )
    target = await _in_thread(lambda: _resolve_member(local, config, pick))
    name = target.name
    if name.family == "fluxnet_ch4":
        raise ToolError(
            "feature_unavailable",
            "Reading FLUXNET-CH4 files arrives in v0.2.",
            details={"reason": "fluxnet_ch4_reader", "file": target.display},
        )
    if name.kind in ("bif", "bifvarinfo"):
        raise ToolError(
            "invalid_argument",
            f"{name.name} is a BIF (metadata) file; read it with amf_read_bif.",
            details={"reason": "bif_file"},
            hint=f"amf_read_bif(file='{target.display}')",
        )
    if not name.is_table:
        raise ToolError(
            "invalid_argument",
            f"{name.name} is not a data table.",
            details={"reason": "not_a_table", "kind": name.kind},
        )
    res = name.resolution
    if args.qc_max is not None and res not in ("HH", "HR"):
        raise ToolError(
            "invalid_argument",
            f"qc_max applies to HH/HR files; at {res} QC is a fraction: use qc_min_fraction.",
            details={"reason": "qc_resolution"},
        )
    if args.qc_min_fraction is not None and res in ("HH", "HR", None):
        raise ToolError(
            "invalid_argument",
            "qc_min_fraction applies to DD and coarser files; at HH/HR use qc_max.",
            details={"reason": "qc_resolution"},
        )
    qc: csvstream.QcRule | None = None
    if args.qc_max is not None:
        qc = csvstream.QcRule("max", float(args.qc_max))
    elif args.qc_min_fraction is not None:
        qc = csvstream.QcRule("min_fraction", args.qc_min_fraction)

    columns = list(args.columns or [])
    if args.view == "subset" and (name.family != "fluxnet" or name.kind != "data"):
        raise ToolError(
            "invalid_argument",
            "view='subset' applies to AmeriFlux FLUXNET (FLUXMET) files; FLUXNET2015 has "
            "its own SUBSET files.",
            details={"reason": "subset_view"},
        )
    want_rows = args.mode == "rows"
    max_rows = min(args.max_rows, limits.preview_max_rows)
    aux = name.kind == "aux_table"

    def run() -> tuple[csvstream.ScanResult, list[str]]:
        chosen = columns
        if args.view == "subset" or not chosen:
            available = _with_stream(target, config, lambda s: csvstream.header(s).values)
            if args.view == "subset":
                fluxnet = fluxnet_dictionary()
                subset = [
                    c
                    for c in available
                    if (e := fluxnet.get(fluxnet_template(c))) is not None and e.subset
                ]
                chosen = [c for c in chosen if c.upper() in subset] if chosen else subset
            elif want_rows:
                chosen = available[:DEFAULT_ROW_COLUMNS]
            else:
                chosen = available[:MAX_SUMMARY_COLUMNS]
        ranges, _ = _ranges(target, chosen)
        result = _with_stream(
            target,
            config,
            lambda s: csvstream.scan(
                s,
                columns=chosen or None,
                start=start,
                end=end,
                want_rows=want_rows,
                offset=args.offset,
                max_rows=max_rows,
                qc=qc,
                ranges=ranges,
                require_timestamps=not aux,
                max_bytes=limits.preview_scan_max_bytes,
                time_budget_s=limits.preview_time_budget_s,
            ),
        )
        return result, chosen

    result, chosen = await _in_thread(run)
    if not chosen and (args.view == "subset"):
        notes.append("No SUBSET variables in this file.")
    _, units = _ranges(target, result.selected)
    total_values = len(result.columns) - len(result.timestamp_columns)
    if not args.columns and len(result.selected) < total_values:
        notes.append(
            f"{len(result.selected)} of {total_values} columns shown; pass columns=[...] for "
            "others."
        )
    if args.view == "subset":
        notes.append(f"SUBSET view: {len(result.selected)} of {total_values} columns.")

    offsets: list[UtcOffsetOut] = []
    if not aux:
        bif = await _in_thread(lambda: _bif_bytes(target, config))
        if bif is not None:
            data, label = bif
            parsed_bif = await _in_thread(
                lambda: bifmod.parse(
                    bifmod.rows_from_bytes(
                        data, label=label, max_bytes=limits.zip_member_max_bytes
                    ),
                    label=label,
                )
            )
            site = (name.site_id or "").casefold()
            offsets = [
                UtcOffsetOut(
                    hours=o.hours, date_start=o.date_start, site_id=o.site_id, comment=o.comment
                )
                for o in bifmod.utc_offsets(parsed_bif)
                if not site or o.site_id.casefold() == site
            ]
            notes.append(f"UTC offset from {label}.")
        else:
            notes.append(
                "No BIF beside this file: the UTC offset is unknown (times are local standard "
                "time, without daylight saving)."
            )
    rows = result.rows if want_rows else None
    row_columns: list[str] | None = None
    if want_rows:
        row_columns = [*result.timestamp_columns, *result.selected]
        if args.to_utc:
            if not offsets:
                notes.append("to_utc ignored: no UTC offset is known for this file.")
            elif not result.rows or len(str(result.rows[0][0])) != 12:
                notes.append("to_utc applies to half-hourly and hourly timestamps only.")
            else:
                pairs = [(o.date_start, o.hours) for o in offsets]
                ts_n = len(result.timestamp_columns)
                row_columns = [*[f"{c}_UTC" for c in result.timestamp_columns], *row_columns]
                converted: list[list[float | str | None]] = []
                for row in result.rows:
                    offset = timestamps.utc_offset_for(str(row[0]), pairs)
                    utc = [
                        timestamps.to_utc(str(v), offset) if offset is not None else None
                        for v in row[:ts_n]
                    ]
                    converted.append([*utc, *row])
                rows = converted
                if len({o.hours for o in offsets}) > 1:
                    notes.append(
                        "The site's UTC offset changed over time; each row uses the one in force."
                    )
    step = result.step_minutes
    expected = timestamps.STEP_MINUTES.get(res or "")
    if step and expected and step != expected:
        if res == "HH" and step == 60:
            notes.append("Hourly data in an HH file: ONEFlux v1.3 names the finest step HH.")
        else:
            notes.append(f"The timestamps give a {step}-minute step; the name says {res}.")
    if result.truncated_reason == "budget":
        notes.append(
            "Scan stopped at the byte or time budget; statistics cover the rows scanned. Narrow "
            "start/end, choose fewer columns, or read the DD or MM file."
        )
    if qc is not None and not result.qc_columns:
        notes.append("No _QC companion columns here; the QC filter changed nothing.")
    if any(s.out_of_range for s in result.stats.values()):
        notes.append("outOfRange counts values beyond the FP Standard range ±5%; they are kept.")
    if name.variant == "SUBSET" and args.view == "subset":
        notes.append("This is already a FLUXNET2015 SUBSET file.")

    page: Page | None = None
    if want_rows:
        total = None if result.more_rows else args.offset + len(result.rows)
        page = Page(
            total=total,
            returned=len(result.rows),
            offset=args.offset,
            limit=max_rows,
            truncated=result.more_rows,
            next_offset=args.offset + len(result.rows) if result.more_rows else None,
            truncated_reason="limit" if result.more_rows else None,
        )
    steps = []
    if result.selected:
        cols = ", ".join(f"'{c}'" for c in result.selected[:3])
        steps.append(f"amf_describe_variables(names=[{cols}]) to decode these columns")
    if page and page.next_offset is not None:
        steps.append(f"amf_preview_data(..., mode='rows', offset={page.next_offset}) for more rows")
    if name.site_id:
        cite = (
            name.product if name.product in ("BASE-BADM", "FLUXNET", "FLUXNET2015") else "BASE-BADM"
        )
        steps.append(f"amf_get_citation(sites=['{name.site_id}'], product='{cite}') to cite it")
    return PreviewResult(
        file_info=FileInfo(
            path=target.local.relative,
            member=target.member,
            family=name.family,
            kind=name.kind,
            product=name.product or None,
            site_id=name.site_id,
            resolution=res,
            version=name.version or (target.container.version if target.container else None),
            step_minutes=step,
            time_range=TimeRange(
                first=timestamps.iso(result.first) if result.first else None,
                last=timestamps.iso(result.last) if result.last else None,
            )
            if result.timestamp_columns
            else None,
            header_lines=result.header_lines,
            columns_total=len(result.columns),
            utc_offsets=offsets,
        ),
        columns=[
            ColumnSummary(
                name=s.name,
                units=units.get(s.name),
                count=s.count,
                missing=s.missing,
                min=s.minimum,
                max=s.maximum,
                mean=round(s.mean, 6) if s.mean is not None else None,
                out_of_range=s.out_of_range if s.name in _ranges(target, [s.name])[0] else None,
                qc_filtered=s.qc_filtered if s.name in result.qc_columns else None,
                text_values=s.text_values or None,
            )
            for s in result.stats.values()
        ],
        row_columns=row_columns,
        rows=rows,
        scan=ScanInfo(
            rows_scanned=result.rows_scanned,
            rows_matched=result.rows_matched,
            bytes_read=result.bytes_read,
            truncated_reason=result.truncated_reason,
            stats_scope="rows" if want_rows else "window",
        ),
        page=page,
        notes=merge_notes(notes),
        next_steps=steps,
        source=source(ctx, derived=["columns", "fileInfo.stepMinutes", "fileInfo.utcOffsets"]),
    )


# ---------------------------------------------------------------------- amf_read_bif


class ReadBifIn(AmfInput):
    file: str | None = Field(
        None,
        max_length=1000,
        description="A BIF xlsx or CSV, or an archive holding one (BASE-BADM, FLUXNET), "
        "relative to a local root. Or give site.",
    )
    site: str | None = Field(None, max_length=20, description="The newest local BIF of this site.")
    groups: list[str] | None = Field(
        None, max_length=40, description="Only these groups, e.g. ['GRP_UTC_OFFSET', 'GRP_DOI']."
    )
    site_id: str | None = Field(
        None, max_length=20, description="In a bulk file (AA-Flx, AA-Net): only this site."
    )
    include_contacts: bool = Field(
        False, description="Emails and addresses, if the server allows it (privacy settings)."
    )
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)


class BifEntryOut(AmfOutput):
    group: str
    group_id: str
    site_id: str
    values: dict[str, str]


class BifCitation(AmfOutput):
    site_id: str
    doi: str | None = None
    citation: str | None = Field(None, description="As recorded in this file's version.")
    data_product: str | None = None


class BifAcknowledgment(AmfOutput):
    site_id: str
    text: str
    source: str = Field(description="GRP_ACKNOWLEDGEMENT or GRP_SITE_FUNDING.")


class BifFileInfo(AmfOutput):
    path: str
    member: str | None = None
    sites_total: int
    sites: list[str]
    entries_total: int
    groups: dict[str, int]


class ReadBifResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "entries"
    file_info: BifFileInfo
    entries: list[BifEntryOut]
    utc_offsets: list[UtcOffsetOut]
    citations: list[BifCitation]
    acknowledgments: list[BifAcknowledgment]
    withheld: int = Field(description="Personal values withheld (emails, addresses, land owners).")
    page: Page


@register_tool(
    "amf_read_bif",
    title="Read a local BADM (BIF) file",
    description=(
        "Read a local BADM Interchange Format file, the site metadata shipped in BASE-BADM "
        "(xlsx) and AmeriFlux FLUXNET (CSV) downloads, also from inside the zip: entries by "
        "group (location, IGBP, team, instruments, disturbance …), UTC offsets with their start "
        "dates, the DOI and citation recorded for that version, and funding acknowledgments. "
        "Emails and addresses are withheld by default. stdio only. Next: call amf_get_citation "
        "for the current citation."
    ),
    input_model=ReadBifIn,
    output_model=ReadBifResult,
    surface="local",
    endpoints=[],
    transports=LOCAL,
    open_world=False,
)
async def amf_read_bif(args: ReadBifIn, ctx: ToolContext) -> ReadBifResult:
    config = ctx.config
    max_bytes = config.limits.zip_member_max_bytes
    notes: list[str] = []
    if args.file:
        local = resolve_file(args.file, config)
    elif args.site:
        found = await asyncio.to_thread(_find_by_site, args.site, "BIF", config)
        local = LocalPath(found.path, found.root)
        notes.append(f"Reading the newest local BIF of {found.name.site_id}: {found.relative}.")
    else:
        raise ToolError("invalid_argument", "Give file or site.", details={"reason": "no_target"})

    def pick(archive: SafeZip, container: FileName) -> str:
        member = pick_bif(archive)
        if member is None:
            raise ToolError(
                "not_found",
                f"{container.name} holds no BIF file.",
                details={"reason": "no_member", "members": [m.name for m in archive.members][:50]},
            )
        return member.name

    target = await _in_thread(lambda: _resolve_member(local, config, pick))
    if target.name.kind not in ("bif", "bifvarinfo"):
        raise ToolError(
            "invalid_argument",
            f"{target.name.name} is not a BIF file.",
            details={"reason": "not_bif", "kind": target.name.kind},
            hint=f"amf_preview_data(file='{target.display}') reads data files.",
        )
    allow = contacts_allowed(config, args.include_contacts)

    def run() -> bifmod.Bif:
        data = _with_stream(target, config, lambda s: s.read(max_bytes + 1))
        if len(data) > max_bytes:
            raise ToolError(
                "invalid_argument", "The BIF file is too large.", details={"reason": "too_large"}
            )
        rows = bifmod.rows_from_bytes(data, label=target.display, max_bytes=max_bytes)
        return bifmod.parse(rows, label=target.display, allow_personal=allow)

    bif = await _in_thread(run)
    entries = bif.entries
    if args.site_id:
        wanted = args.site_id.strip().casefold()
        entries = [e for e in entries if e.site_id.casefold() == wanted]
        if not entries:
            notes.append(f"No entries for {args.site_id} in this file.")
    groups = {g.strip().upper() for g in args.groups or []}
    shown = [e for e in entries if not groups or e.group.upper() in groups]
    if groups and not shown:
        notes.append("No entries in those groups; see fileInfo.groups for what the file holds.")
    page_items, page = paginate(shown, offset=args.offset, limit=args.limit)
    selected = bifmod.Bif(entries=entries, withheld=bif.withheld)
    offsets = [
        UtcOffsetOut(hours=o.hours, date_start=o.date_start, site_id=o.site_id, comment=o.comment)
        for o in bifmod.utc_offsets(selected)
    ]
    citations: list[BifCitation] = []
    acknowledgments: list[BifAcknowledgment] = []
    for site in selected.sites:
        site_entries = [e for e in entries if e.site_id == site]
        doi_entries = [e for e in site_entries if e.group == "GRP_DOI"]
        if doi_entries:
            citations.append(
                BifCitation(
                    site_id=site,
                    doi=bifmod.first_value(doi_entries, "DOI"),
                    citation=bifmod.first_value(doi_entries, "DOI_CITATION"),
                    data_product=bifmod.first_value(doi_entries, "DOI_DATAPRODUCT"),
                )
            )
        for group, variable in (
            ("GRP_ACKNOWLEDGEMENT", "ACKNOWLEDGEMENT"),
            ("GRP_SITE_FUNDING", "SITE_FUNDING"),
        ):
            for e in site_entries:
                if e.group == group and e.values.get(variable):
                    acknowledgments.append(
                        BifAcknowledgment(site_id=site, text=e.values[variable], source=group)
                    )
    if bif.withheld:
        notes.append(
            f"{bif.withheld} personal values withheld (emails, postal and shipping addresses, "
            "private land owners)."
        )
        if args.include_contacts:
            notes.append(CONTACTS_WITHHELD_NOTE)
    if citations:
        notes.append(
            "The citation in a BIF is the one recorded for that file's version; amf_get_citation "
            "gives the current one."
        )
    steps = []
    if selected.sites and len(selected.sites) <= 50:
        site_list = ", ".join(f"'{s}'" for s in selected.sites[:5])
        steps.append(f"amf_get_citation(sites=[{site_list}]) for the current citations")
    if page.next_offset is not None:
        steps.append(f"amf_read_bif(..., offset={page.next_offset}) for more entries")
    sites = selected.sites
    return ReadBifResult(
        file_info=BifFileInfo(
            path=target.local.relative,
            member=target.member,
            sites_total=len(sites),
            sites=sites[:50],
            entries_total=len(entries),
            groups=dict(Counter(e.group for e in entries).most_common()),
        ),
        entries=[
            BifEntryOut(group=e.group, group_id=e.group_id, site_id=e.site_id, values=e.values)
            for e in page_items
        ],
        utc_offsets=offsets,
        citations=citations[:50],
        acknowledgments=acknowledgments[:100],
        withheld=bif.withheld,
        page=page,
        notes=merge_notes(notes),
        next_steps=steps,
        source=source(ctx),
    )


__all__ = ["amf_list_files", "amf_preview_data", "amf_read_bif"]
