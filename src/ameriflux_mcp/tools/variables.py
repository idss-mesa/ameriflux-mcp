"""Variables: ``amf_search_variables`` and ``amf_describe_variables`` (build step 5)."""

from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Sequence
from typing import ClassVar, Literal

from pydantic import Field, field_validator

from ameriflux_mcp.ameriflux.catalog import SiteRecord, words
from ameriflux_mcp.ameriflux.resolve import resolve_site
from ameriflux_mcp.ameriflux.variables.coverage import COVERAGE_URL, coverage
from ameriflux_mcp.ameriflux.variables.dictionaries import (
    HEIGHT_DIRECTIONS,
    RESOLUTIONS,
    SIGN_CONVENTIONS,
    FluxnetVariable,
    FpList,
    FpVariable,
    fluxnet_dictionary,
    fluxnet_sources,
    fp_variables,
)
from ameriflux_mcp.ameriflux.variables.grammar import ParsedName, parse
from ameriflux_mcp.ameriflux.variables.heights import HEIGHTS_PAGE, heights_file
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import AmeriFluxApiError
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Page, ToolResultBase
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import compact_years, merge_notes, paginate, source
from ameriflux_mcp.tools.sites import site_index

Dictionary = Literal["fp", "fluxnet", "fluxnet_fullset", "fluxnet_subset", "all"]
ResolutionArg = Literal["HH", "DD", "WW", "MM", "YY"]
FP_ENDPOINT = "GET amfcdn.lbl.gov/api/v1/fp_var"
_RESOLUTION_ALIASES = {"HR": "HH", "D": "DD", "W": "WW", "M": "MM", "Y": "YY"}


def _resolution(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().upper()
    return _RESOLUTION_ALIASES.get(text, text)


def _fluxnet_in(variable: FluxnetVariable, dictionary: Dictionary) -> bool:
    if dictionary == "fluxnet":
        return bool(variable.oneflux)
    if dictionary == "fluxnet_fullset":
        return variable.fullset
    if dictionary == "fluxnet_subset":
        return variable.subset
    return dictionary == "all"


def _fluxnet_dictionaries(variable: FluxnetVariable) -> list[str]:
    out = []
    if variable.oneflux:
        out.append("fluxnet")
    if variable.fullset:
        out.append("fluxnet_fullset")
    if variable.subset:
        out.append("fluxnet_subset")
    return out


# ---------------------------------------------------------------------- amf_search_variables


class SearchVariablesIn(AmfInput):
    query: str | None = Field(
        None,
        max_length=200,
        description="Words matched against name, description and units (prefixes count: "
        "'soil temp', 'GPP', 'methane').",
    )
    dictionary: Dictionary = Field(
        "all",
        description="fp (FP Standard, BASE), fluxnet (AmeriFlux FLUXNET, ONEFlux v1.3), "
        "fluxnet_fullset / fluxnet_subset (FLUXNET2015), or all.",
    )
    category: str | None = Field(
        None,
        max_length=60,
        description="FP type (GASES, MET_RAD, MET_SOIL, …) or FLUXNET section (PARTITIONING, "
        "NET ECOSYSTEM EXCHANGE, …); prefixes count.",
    )
    resolution: str | None = Field(
        None,
        description="HH (also HR), DD, WW, MM or YY: FLUXNET variables available at it, with "
        "its units.",
    )
    limit: int = Field(25, ge=1, le=200)
    offset: int = Field(0, ge=0)

    @field_validator("resolution")
    @classmethod
    def _res(cls, value: str | None) -> str | None:
        res = _resolution(value)
        if res is not None and res not in RESOLUTIONS:
            raise ValueError("resolution must be HH, DD, WW, MM or YY")
        return res


class PlausibleRange(AmfOutput):
    min: float | None = None
    max: float | None = None


class VariableSummary(AmfOutput):
    name: str
    dictionary: list[str] = Field(description="fp, fluxnet, fluxnet_fullset, fluxnet_subset.")
    category: str | None = Field(None, description="FP type or FLUXNET section.")
    description: str | None = None
    units: str | None = Field(
        None, description="FP units, or FLUXNET units at the requested resolution."
    )
    units_by_resolution: dict[str, str | None] | None = Field(
        None, description="FLUXNET units per resolution (null where the variable is absent)."
    )
    plausible_range: PlausibleRange | None = Field(
        None, description="FP Standard QA/QC range (Min, Max)."
    )
    in_subset: bool | None = Field(None, description="FLUXNET: part of the SUBSET product.")


class VariableFacets(AmfOutput):
    dictionary: dict[str, int]
    category: dict[str, int]


class SearchVariablesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "variables"
    variables: list[VariableSummary]
    facets: VariableFacets
    page: Page


def _score(query_words: Sequence[str], name: str, text: str) -> float:
    """0 = no match; name hits rank above description hits."""
    if not query_words:
        return 1.0
    name_words = words(name.replace("_", " "))
    text_words = words(text)
    total = 0.0
    for word in query_words:
        if name.lower() == word or word in name_words:
            total += 3
        elif any(w.startswith(word) for w in name_words):
            total += 2
        elif any(w.startswith(word) for w in text_words):
            total += 1
        else:
            return 0.0
    return total


@register_tool(
    "amf_search_variables",
    title="Search the FP Standard and FLUXNET variable dictionaries",
    description=(
        "Find variable names in the FP Standard list (AmeriFlux BASE, live, with QA/QC ranges) "
        "and the FLUXNET dictionaries (AmeriFlux FLUXNET from ONEFlux v1.3; FLUXNET2015 FULLSET "
        "and SUBSET), by words, category or resolution. FLUXNET units change with resolution "
        "(NEE is umol m-2 s-1 at HH, gC m-2 d-1 at DD), so each result lists units per "
        "resolution and SUBSET membership. Next: call amf_describe_variables on the names."
    ),
    input_model=SearchVariablesIn,
    output_model=SearchVariablesResult,
    surface="variables",
    endpoints=[FP_ENDPOINT],
)
async def amf_search_variables(args: SearchVariablesIn, ctx: ToolContext) -> SearchVariablesResult:
    query_words = words(args.query)
    category = (args.category or "").strip().upper().replace("-", "_")
    notes: list[str] = []
    scored: list[tuple[float, VariableSummary]] = []
    fp_list: FpList | None = None
    if args.dictionary in ("fp", "all") and args.resolution is None:
        fp_list = await fp_variables(ctx)
        notes.extend(fp_list.notes)
        for v in fp_list.variables:
            if category and not (v.type or "").upper().startswith(category):
                continue
            score = _score(query_words, v.name, f"{v.description or ''} {v.units or ''}")
            if score:
                scored.append(
                    (
                        score,
                        VariableSummary(
                            name=v.name,
                            dictionary=["fp"],
                            category=v.type,
                            description=v.description,
                            units=v.units,
                            plausible_range=PlausibleRange(min=v.min, max=v.max)
                            if v.min is not None or v.max is not None
                            else None,
                        ),
                    )
                )
    elif args.dictionary in ("fp", "all"):
        notes.append("resolution applies to the FLUXNET dictionaries only; FP variables skipped.")
    if args.dictionary != "fp":
        for fx in fluxnet_dictionary().values():
            if not _fluxnet_in(fx, args.dictionary):
                continue
            if args.dictionary == "all" and not (fx.oneflux or fx.fullset):
                continue
            if category and not (fx.section or "").upper().replace(" ", "_").startswith(category):
                continue
            if args.resolution and not fx.available_at(args.resolution):
                continue
            units_text = " ".join(u for u in fx.units.values() if u)
            score = _score(query_words, fx.name, f"{fx.description or ''} {units_text}")
            if score:
                scored.append(
                    (
                        score,
                        VariableSummary(
                            name=fx.name,
                            dictionary=_fluxnet_dictionaries(fx),
                            category=fx.section,
                            description=fx.description,
                            units=fx.units.get(args.resolution) if args.resolution else None,
                            units_by_resolution=dict(fx.units),
                            in_subset=fx.subset,
                        ),
                    )
                )
    scored.sort(key=lambda item: (-item[0], item[1].name, item[1].dictionary))
    matched = [item for _, item in scored]
    facets = VariableFacets(
        dictionary=dict(Counter(d for v in matched for d in v.dictionary).most_common()),
        category=dict(Counter(v.category or "none" for v in matched).most_common()),
    )
    page_items, page = paginate(matched, offset=args.offset, limit=args.limit)
    if not matched:
        notes.append("No variable matches; try fewer words, another dictionary or no category.")
    if any("XX" in v.name or "#" in v.name for v in page_items):
        notes.append(
            "XX stands for a percentile (05, 16, 25, 50, 75, 84, 95) and # for a soil layer "
            "index (1 = shallowest): NEE_VUT_XX is NEE_VUT_05 … NEE_VUT_95."
        )
    steps = []
    if page_items:
        names = ", ".join(f"'{v.name}'" for v in page_items[:3])
        steps.append(f"amf_describe_variables(names=[{names}]) for units, QC and grammar")
    if page.next_offset is not None:
        steps.append(f"amf_search_variables(..., offset={page.next_offset}) for the next page")
    return SearchVariablesResult(
        variables=page_items,
        facets=facets,
        page=page,
        notes=notes,
        next_steps=steps,
        source=source(ctx, derived=["facets"]),
    )


# ---------------------------------------------------------------------- amf_describe_variables


class DescribeVariablesIn(AmfInput):
    names: list[str] = Field(
        min_length=1,
        max_length=20,
        description="Variable names as in file headers: TA_F_1_1_1, FC_PI_F_1_1_A, "
        "GPP_NT_VUT_REF, NEE_VUT_05, TS_F_MDS_2_QC …",
    )
    resolution: str | None = Field(
        None,
        description="HH (also HR), DD, WW, MM or YY: units and QC meaning at this resolution "
        "(FLUXNET). Default: all resolutions.",
    )
    site: str | None = Field(
        None,
        max_length=200,
        description="A site (ID, NEON code or name): adds whether it measures the variable, "
        "its measurement heights and instruments, and yearly coverage.",
    )

    @field_validator("resolution")
    @classmethod
    def _res(cls, value: str | None) -> str | None:
        res = _resolution(value)
        if res is not None and res not in RESOLUTIONS:
            raise ValueError("resolution must be HH, DD, WW, MM or YY")
        return res


class TokenOut(AmfOutput):
    token: str
    kind: str
    meaning: str


class PositionOut(AmfOutput):
    kind: str = Field(
        description="sensor (_H_V_R), replicate_average (_H_V_A) or layer_average (_#)."
    )
    h: int | None = None
    v: int | None = None
    r: int | None = None
    layer: int | None = None
    statistic: str | None = Field(None, description="SD or N of an aggregate.")


class BaseDefinition(AmfOutput):
    name: str
    description: str | None = None
    units: str | None = None
    type: str | None = None
    plausible_range: PlausibleRange | None = None
    height_direction: str | None = None


class FluxnetDefinition(AmfOutput):
    template: str = Field(description="Dictionary key, e.g. NEE_VUT_XX for NEE_VUT_05.")
    description: str | None = None
    section: str | None = None
    units: str | None = Field(None, description="Units at the requested resolution.")
    units_by_resolution: dict[str, str | None]
    notes_by_resolution: dict[str, str] = Field(
        default_factory=dict,
        description="Aggregation and QC meaning per resolution (e.g. HH 0-3 flags, DD fractions).",
    )
    in_fullset: bool
    in_subset: bool
    oneflux_resolutions: list[str] = Field(
        description="Resolutions of the AmeriFlux FLUXNET product (ONEFlux v1.3) defining it."
    )


class HeightOut(AmfOutput):
    variable: str
    height_m: float | None = None
    instrument: str | None = None
    instrument2: str | None = None
    start_date: str | None = None
    comment: str | None = None
    base_version: str | None = None


class CoverageOut(AmfOutput):
    variable: str
    gap_filled: bool
    years: str | None = Field(None, description="Years with any data, compact.")
    mean_fraction: float | None = Field(
        None, description="Mean fraction of those years with data (0-1)."
    )


class AtSite(AmfOutput):
    site_id: str
    in_base_variables: bool | None = Field(
        None, description="The base name is in the site's BASE variable list (catalog)."
    )
    heights: list[HeightOut] | None = None
    heights_file: str | None = None
    coverage: list[CoverageOut] | None = None
    coverage_snapshot: str | None = Field(None, description="amerifluxr snapshot date.")


class VariableDescription(AmfOutput):
    name: str
    recognized: bool = Field(
        description="True when the base name is FP Standard and the name parses, or the name is "
        "in a FLUXNET dictionary."
    )
    grammar: str = Field(description="base (FP Standard qualifiers), fluxnet, or unknown.")
    basename: str | None = None
    base: BaseDefinition | None = None
    qualifiers: list[TokenOut] = Field(default_factory=list)
    position: PositionOut | None = None
    units: str | None = Field(
        None, description="Units of this name (BASE), or at the requested resolution (FLUXNET)."
    )
    fluxnet: FluxnetDefinition | None = None
    sign_convention: str | None = None
    unknown_tokens: list[str] = Field(default_factory=list)
    did_you_mean: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    at_site: AtSite | None = None


class DescribeVariablesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "variables"
    budget_next_step: ClassVar[str | None] = (
        "amf_describe_variables(names=[...]) with fewer names (trimmed from {next_offset})"
    )
    variables: list[VariableDescription]
    page: Page


def _base_units(parsed: ParsedName, fp: FpVariable | None) -> str | None:
    if fp is None:
        return None
    if "QC" in parsed.general:
        return "nondimensional (quality flag)"
    if "IU" in parsed.general:
        return "instrument units (not the FP Standard units)"
    if parsed.position is not None and parsed.position.statistic == "N":
        return "count"
    return fp.units


def _fluxnet_definition(
    template: str, variable: FluxnetVariable, resolution: str | None
) -> FluxnetDefinition:
    notes = dict(variable.notes)
    units = dict(variable.units)
    if resolution:
        notes = {k: v for k, v in notes.items() if k == resolution}
    return FluxnetDefinition(
        template=template,
        description=variable.description,
        section=variable.section,
        units=units.get(resolution) if resolution else None,
        units_by_resolution=units,
        notes_by_resolution=notes,
        in_fullset=variable.fullset,
        in_subset=variable.subset,
        oneflux_resolutions=list(variable.oneflux),
    )


def _matches(row_variable: str, parsed: ParsedName, names: frozenset[str]) -> bool:
    if row_variable.upper() == parsed.name:
        return True
    if parsed.position is not None:
        return False  # a positional name asks for that sensor only
    other = parse(row_variable, names)
    return other.basename == parsed.basename


def _describe(
    name: str,
    *,
    fp_by_name: dict[str, FpVariable],
    fp_names: frozenset[str],
    resolution: str | None,
) -> VariableDescription:
    parsed = parse(name, fp_names)
    fluxnet = fluxnet_dictionary()
    fp = fp_by_name.get(parsed.basename or "")
    template = parsed.template if parsed.template in fluxnet else None
    if template is None and parsed.name in fluxnet:
        template = parsed.name
    recognized = (parsed.grammar == "base") or template is not None
    notes = list(parsed.notes)
    fluxnet_def = _fluxnet_definition(template, fluxnet[template], resolution) if template else None
    if parsed.grammar == "base" and fluxnet_def is not None:
        notes.append(
            f"{parsed.name} is also a FLUXNET name: in BASE files it follows the FP Standard "
            "qualifiers below; in FLUXNET files read the fluxnet definition."
        )
    if fluxnet_def is not None and fluxnet_def.oneflux_resolutions == [] and fluxnet_def.in_fullset:
        notes.append(
            "FLUXNET2015 only: the AmeriFlux FLUXNET product (ONEFlux v1.3) does not define it."
        )
    if fluxnet_def is not None and resolution and fluxnet_def.units is None:
        notes.append(f"Not available at {resolution}.")
    if parsed.grammar == "fluxnet" and fluxnet_def is None:
        notes.append("Every token is known but the name is in no FLUXNET dictionary.")
    did_you_mean: list[str] = []
    if not recognized:
        pool = sorted(fp_names | set(fluxnet))
        did_you_mean = difflib.get_close_matches(parsed.name, pool, n=3, cutoff=0.6)
    fluxnet_units = fluxnet_def.units if fluxnet_def else None
    units = _base_units(parsed, fp) if parsed.grammar == "base" else fluxnet_units
    sign = SIGN_CONVENTIONS.get(parsed.basename or "") if not parsed.is_qc else None
    position = parsed.position
    return VariableDescription(
        name=parsed.name,
        recognized=recognized,
        grammar=parsed.grammar,
        basename=parsed.basename,
        base=BaseDefinition(
            name=fp.name,
            description=fp.description,
            units=fp.units,
            type=fp.type,
            plausible_range=PlausibleRange(min=fp.min, max=fp.max)
            if fp.min is not None or fp.max is not None
            else None,
            height_direction=HEIGHT_DIRECTIONS.get(fp.height_direction or ""),
        )
        if fp
        else None,
        qualifiers=[TokenOut(token=t.text, kind=t.kind, meaning=t.meaning) for t in parsed.tokens],
        position=PositionOut(
            kind=position.kind,
            h=position.h,
            v=position.v,
            r=position.r,
            layer=position.layer,
            statistic=position.statistic,
        )
        if position
        else None,
        units=units,
        fluxnet=fluxnet_def,
        sign_convention=sign,
        unknown_tokens=list(parsed.unknown),
        did_you_mean=did_you_mean,
        notes=notes,
    )


async def _at_site(
    ctx: ToolContext,
    record: SiteRecord,
    descriptions: list[VariableDescription],
    fp_names: frozenset[str],
) -> list[str]:
    """Fill ``at_site`` for each described name; returns notes for the whole result."""
    notes: list[str] = []
    heights = cover = None
    if "ameriflux" not in record.collections:
        notes.append(
            f"{record.site_id} is not an AmeriFlux site: no BASE heights or coverage exist for it."
        )
    else:
        try:
            heights = await heights_file(ctx)
        except AmeriFluxApiError as exc:
            notes.append(
                f"Measurement heights unavailable ({exc.service}: {exc.status or exc.kind})."
            )
        try:
            cover = await coverage(ctx)
        except AmeriFluxApiError as exc:
            notes.append(
                f"Coverage snapshot unavailable ({exc.service}: {exc.status or exc.kind})."
            )
    if cover is not None:
        notes.append(
            f"Coverage is amerifluxr's snapshot of {cover.created or 'unknown date'}; it lags the "
            "current BASE release."
        )
    height_rows = heights.site_rows(record.site_id) if heights else []
    cover_rows = cover.site_rows(record.site_id) if cover else []
    measured = set(record.base_variables)
    for item in descriptions:
        parsed = parse(item.name, fp_names)
        at = AtSite(
            site_id=record.site_id,
            in_base_variables=(item.basename in measured) if measured else None,
        )
        if heights is not None:
            at.heights = [
                HeightOut(
                    variable=h.variable,
                    height_m=h.height_m,
                    instrument=h.instrument,
                    instrument2=h.instrument2,
                    start_date=h.start_date,
                    comment=h.comment,
                    base_version=h.base_version,
                )
                for h in height_rows
                if _matches(h.variable, parsed, fp_names)
            ][:30]
            at.heights_file = heights.url
        if cover is not None:
            entries = []
            for c in cover_rows:
                if not _matches(c.variable, parsed, fp_names):
                    continue
                fractions = list(c.years.values())
                entries.append(
                    CoverageOut(
                        variable=c.variable,
                        gap_filled=c.gap_filled,
                        years=compact_years(list(c.years)),
                        mean_fraction=round(sum(fractions) / len(fractions), 3)
                        if fractions
                        else None,
                    )
                )
            at.coverage = entries[:30]
            at.coverage_snapshot = cover.created
        item.at_site = at
    return notes


@register_tool(
    "amf_describe_variables",
    title="Describe variable names: grammar, units, QC and sites",
    description=(
        "Decode up to 20 variable names from BASE or FLUXNET files: base name and FP Standard "
        "definition with QA/QC range, qualifiers (_PI, _QC, _F, _IU), position (_H_V_R, _H_V_A, "
        "_#), FLUXNET processing tokens (MDS, VUT/CUT, NT/DT, REF, percentiles), units and QC "
        "meaning per resolution, sign conventions. With site: whether the site measures it, "
        "sensor heights and instruments, yearly coverage. Next: call amf_get_availability for "
        "the site's years."
    ),
    input_model=DescribeVariablesIn,
    output_model=DescribeVariablesResult,
    surface="variables",
    endpoints=[FP_ENDPOINT],
)
async def amf_describe_variables(
    args: DescribeVariablesIn, ctx: ToolContext
) -> DescribeVariablesResult:
    fp_list = await fp_variables(ctx)
    fp_by_name = fp_list.by_name()
    fp_names = frozenset(fp_by_name)
    names = list(dict.fromkeys(n.strip().upper() for n in args.names if n.strip()))
    descriptions = [
        _describe(n, fp_by_name=fp_by_name, fp_names=fp_names, resolution=args.resolution)
        for n in names
    ]
    notes = list(fp_list.notes)
    resolved = []
    steps: list[str] = []
    if args.site:
        index = await site_index(ctx)
        resolution = resolve_site(args.site, index)
        if resolution.resolved:
            resolved.append(resolution.resolved)
        notes.extend(resolution.notes)
        notes.extend(await _at_site(ctx, resolution.record, descriptions, fp_names))
        steps.append(
            f"amf_get_availability(sites=['{resolution.site_id}']) for the years of each product"
        )
    unknown = [d.name for d in descriptions if not d.recognized]
    if unknown:
        notes.append(f"Not recognized: {', '.join(unknown)} (see didYouMean).")
        steps.append("amf_search_variables(query='…') to find the right name")
    if any(d.fluxnet for d in descriptions):
        sources = fluxnet_sources()
        notes.append(
            "FLUXNET definitions: FLUXNET2015 webdoc dictionaries "
            f"({sources['fullset']['url'].rsplit('/', 1)[-1]}) and ONEFlux "
            f"{sources['oneflux']['commit'][:7]}."
        )
    page_items, page = paginate(descriptions, offset=0, limit=len(descriptions))
    derived = ["grammar", "qualifiers", "position"]
    if args.site:
        derived.append("atSite")
    return DescribeVariablesResult(
        variables=page_items,
        page=page,
        resolved=resolved,
        notes=merge_notes(notes),
        next_steps=steps,
        source=source(ctx, derived=derived),
    )


__all__ = [
    "COVERAGE_URL",
    "HEIGHTS_PAGE",
    "amf_describe_variables",
    "amf_search_variables",
]
