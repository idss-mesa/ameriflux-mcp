"""BADM: ``amf_get_badm`` (build step 5).

The Biological, Ancillary, Disturbance and Metadata (BADM) a site's API records carry,
grouped by BADM group: site (GRP_LOCATION, GRP_IGBP, GRP_CLIM_AVG, tower dates), team
(GRP_TEAM_MEMBER), disturbance and management (the catalog's summary of GRP_DM),
funding and organizations (the DOI record's sponsors and contributors), reference
papers (GRP_REFERENCE_PAPER via the DOI record) and instruments (the measurement-height
file, standing in for GRP_INST/GRP_VAR_INFO). The complete BADM, with every group and
its dates, ships as the BIF file inside each BASE-BADM download.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from ameriflux_mcp.ameriflux.citation import DoiRecord, doi_record
from ameriflux_mcp.ameriflux.privacy import CONTACTS_WITHHELD_NOTE, contacts_allowed
from ameriflux_mcp.ameriflux.reference import igbp_label, koeppen_caveat, koeppen_label
from ameriflux_mcp.ameriflux.resolve import resolve_site
from ameriflux_mcp.ameriflux.variables.grammar import parse
from ameriflux_mcp.ameriflux.variables.heights import heights_file
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import AmeriFluxApiError
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Page, ToolResultBase
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import paginate, source
from ameriflux_mcp.tools.sites import CATALOG_ENDPOINTS, TeamEntry, site_index, site_policy

BadmSection = Literal["site", "team", "disturbance", "funding", "references", "instruments"]
SECTIONS: tuple[BadmSection, ...] = (
    "site",
    "team",
    "disturbance",
    "funding",
    "references",
    "instruments",
)
FULL_BADM_NOTE = (
    "This is the BADM the AmeriFlux API exposes. The complete BADM (every group, with dates) "
    "is the BIF file inside each BASE-BADM download."
)


class GetBadmIn(AmfInput):
    site: str = Field(
        max_length=200, description="Site ID (any case), NEON code, FLUXNET2015 old ID or name."
    )
    include: list[BadmSection] | None = Field(
        None,
        description="Sections; default all: site, team, disturbance, funding, references, "
        "instruments.",
    )
    variables: list[str] | None = Field(
        None,
        max_length=20,
        description="Instruments: only these base names or exact variables (e.g. ['TA', "
        "'SWC_1_1_1']).",
    )
    references_limit: int = Field(20, ge=1, le=200, description="Reference papers per page.")
    references_offset: int = Field(0, ge=0)
    include_contacts: bool = Field(
        False, description="Team emails, if the server allows it (privacy.allow_contact_emails)."
    )


class SiteGroup(AmfOutput):
    latitude: float | None = Field(None, description="GRP_LOCATION LOCATION_LAT.")
    longitude: float | None = Field(None, description="GRP_LOCATION LOCATION_LONG.")
    elevation_m: float | None = Field(None, description="GRP_LOCATION LOCATION_ELEV.")
    country: str | None = None
    state: str | None = None
    igbp: str | None = Field(None, description="GRP_IGBP.")
    igbp_label: str | None = None
    koeppen: str | None = Field(None, description="GRP_CLIM_AVG CLIMATE_KOEPPEN.")
    koeppen_label: str | None = None
    koeppen_note: str | None = None
    mat_c: float | None = Field(None, description="GRP_CLIM_AVG MAT (deg C).")
    map_mm: float | None = Field(None, description="GRP_CLIM_AVG MAP (mm).")
    tower_start: str | None = None
    tower_end: str | None = None
    url: str | None = Field(None, description="The site's own web page (URL_AMERIFLUX).")
    description: str | None = None


class FundingGroup(AmfOutput):
    sponsors: list[str] = Field(
        default_factory=list, description="DOI_SPONSOR_ORGANIZATION: funding to acknowledge."
    )
    organizations: list[str] = Field(
        default_factory=list, description="DOI_CONTRIBUTOR_ORGANIZATION."
    )
    doi: str | None = None


class ReferenceOut(AmfOutput):
    citation: str | None = None
    doi: str | None = None
    usage: str | None = None


class ReferencesGroup(AmfOutput):
    items: list[ReferenceOut]
    page: Page


class InstrumentOut(AmfOutput):
    variable: str
    height_m: float | None = Field(None, description="Metres; negative is depth.")
    instrument: str | None = None
    instrument2: str | None = None
    start_date: str | None = None
    comment: str | None = Field(None, description="As written; some teams put a date here.")
    base_version: str | None = None


class InstrumentsGroup(AmfOutput):
    file: str
    date: str
    items: list[InstrumentOut]
    total: int


class GetBadmResult(ToolResultBase):
    budget_list: ClassVar[str | None] = None
    site_id: str
    name: str
    policy: str | None = None
    site: SiteGroup | None = None
    team: list[TeamEntry] | None = None
    disturbance: list[str] | None = Field(
        None, description="Dominant disturbance and management (catalog summary of GRP_DM)."
    )
    flux_measurements: list[str] | None = Field(None, description="Flux gas species measured.")
    funding: FundingGroup | None = None
    references: ReferencesGroup | None = None
    instruments: InstrumentsGroup | None = None


MAX_INSTRUMENTS = 150


def _wants(variable: str, filters: list[str]) -> bool:
    """An exact variable (``SWC_1_1_1``) or a base name (``P`` but not ``P_RAIN``)."""
    upper = variable.upper()
    return upper in filters or parse(upper).basename in filters


@register_tool(
    "amf_get_badm",
    title="Get a site's BADM metadata",
    description=(
        "A site's Biological, Ancillary, Disturbance and Metadata as the API exposes it, by "
        "group: location, IGBP and climate, tower dates, team (no emails by default), "
        "disturbance and management, funding sponsors and organizations (needed to acknowledge "
        "Legacy sites), reference papers, and instruments with measurement heights. The full "
        "BADM ships as the BIF file in BASE-BADM downloads. Next: call amf_get_citation to cite "
        "the site."
    ),
    input_model=GetBadmIn,
    output_model=GetBadmResult,
    surface="metadata",
    endpoints=[*CATALOG_ENDPOINTS, "GET amfcdn.lbl.gov/api/v1/DOI/{site}/{product}"],
)
async def amf_get_badm(args: GetBadmIn, ctx: ToolContext) -> GetBadmResult:
    index = await site_index(ctx)
    resolution = resolve_site(args.site, index)
    record = resolution.record
    sections = set(args.include or SECTIONS)
    notes = list(resolution.notes)
    amf = "ameriflux" in record.collections

    result = GetBadmResult(
        site_id=record.site_id,
        name=record.name,
        policy=site_policy(record),
        resolved=[resolution.resolved] if resolution.resolved else [],
    )
    if "site" in sections:
        result.site = SiteGroup(
            latitude=record.latitude,
            longitude=record.longitude,
            elevation_m=record.elevation_m,
            country=record.country,
            state=record.state,
            igbp=record.igbp,
            igbp_label=igbp_label(record.igbp),
            koeppen=record.koeppen,
            koeppen_label=koeppen_label(record.koeppen),
            koeppen_note=koeppen_caveat(record.koeppen),
            mat_c=record.mat_c,
            map_mm=record.map_mm,
            tower_start=record.tower_start,
            tower_end=record.tower_end,
            url=record.url,
            description=record.description,
        )
    if "team" in sections:
        show_email = contacts_allowed(ctx.config, args.include_contacts)
        result.team = [
            TeamEntry(
                name=m.name,
                role=m.role,
                institution=m.institution or None,
                email=m.email if show_email else None,
            )
            for m in record.team
        ]
        if args.include_contacts and not show_email:
            notes.append(CONTACTS_WITHHELD_NOTE)
    if "disturbance" in sections:
        result.disturbance = list(record.disturbance)
        result.flux_measurements = list(record.gas_species)

    doi: DoiRecord | None = None
    if sections & {"funding", "references"}:
        segment = "AmeriFlux" if amf else "FLUXNET2015" if record.fluxnet2015 else None
        if segment is None:
            notes.append(f"{record.site_id} has no DOI record to read funding or references from.")
        else:
            try:
                doi = await doi_record(ctx, record.site_id, segment)
            except AmeriFluxApiError as exc:
                notes.append(
                    f"The DOI record was unavailable ({exc.service}: {exc.status or exc.kind}); "
                    "funding and references are missing."
                )
            if doi is None and not any("DOI record" in n for n in notes):
                notes.append(f"AmeriFlux has no {segment} DOI record for {record.site_id}.")
    if doi is not None and "funding" in sections:
        result.funding = FundingGroup(
            sponsors=list(doi.sponsors), organizations=list(doi.organizations), doi=doi.doi
        )
        if not doi.sponsors and site_policy(record) == "LEGACY":
            notes.append(
                "No sponsor in the DOI record; the Legacy policy asks you to acknowledge site "
                "funding: see GRP_ACKNOWLEDGEMENT in the BIF file."
            )
    if doi is not None and "references" in sections:
        refs = [ReferenceOut(citation=r.paper, doi=r.doi, usage=r.usage) for r in doi.references]
        items, page = paginate(refs, offset=args.references_offset, limit=args.references_limit)
        result.references = ReferencesGroup(items=items, page=page)

    if "instruments" in sections:
        if not amf:
            notes.append("Instruments and heights exist only for AmeriFlux BASE sites.")
        else:
            try:
                heights = await heights_file(ctx)
            except AmeriFluxApiError as exc:
                notes.append(
                    f"Measurement heights unavailable ({exc.service}: {exc.status or exc.kind})."
                )
            else:
                filters = [v.strip().upper() for v in args.variables or [] if v.strip()]
                rows = [
                    h
                    for h in heights.site_rows(record.site_id)
                    if not filters or _wants(h.variable, filters)
                ]
                result.instruments = InstrumentsGroup(
                    file=heights.url,
                    date=heights.date,
                    total=len(rows),
                    items=[
                        InstrumentOut(
                            variable=h.variable,
                            height_m=h.height_m,
                            instrument=h.instrument,
                            instrument2=h.instrument2,
                            start_date=h.start_date,
                            comment=h.comment,
                            base_version=h.base_version,
                        )
                        for h in rows[:MAX_INSTRUMENTS]
                    ],
                )
                if len(rows) > MAX_INSTRUMENTS:
                    notes.append(
                        f"{len(rows)} instrument rows; the first {MAX_INSTRUMENTS} are shown. "
                        "Pass variables=[...] to narrow them."
                    )
    notes.append(FULL_BADM_NOTE)
    steps = [f"amf_get_citation(sites=['{record.site_id}']) for the citation and obligations"]
    if result.references and result.references.page.next_offset is not None:
        steps.append(
            f"amf_get_badm(site='{record.site_id}', include=['references'], "
            f"references_offset={result.references.page.next_offset}) for more papers"
        )
    if result.instruments and result.instruments.items:
        steps.append(
            f"amf_describe_variables(names=['{result.instruments.items[0].variable}'], "
            f"site='{record.site_id}') to decode a variable"
        )
    result.notes = notes
    result.next_steps = steps
    result.source = source(ctx)
    return result


__all__ = ["amf_get_badm"]
