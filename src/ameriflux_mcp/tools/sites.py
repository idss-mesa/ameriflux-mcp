"""Site discovery: ``amf_search_sites`` and ``amf_get_site`` (build step 4)."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from typing import ClassVar, Literal

from pydantic import Field, field_validator

from ameriflux_mcp.ameriflux.catalog import SiteIndex, SiteRecord, TierYears, name_score, words
from ameriflux_mcp.ameriflux.privacy import CONTACTS_WITHHELD_NOTE, contacts_allowed
from ameriflux_mcp.ameriflux.products import (
    Policy,
    Product,
    normalize_policy,
    normalize_product,
    validate,
)
from ameriflux_mcp.ameriflux.reference import (
    igbp_label,
    koeppen_caveat,
    koeppen_label,
    lter_link,
)
from ameriflux_mcp.ameriflux.resolve import resolve_site
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Page, ToolResultBase
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import (
    compact_years,
    paginate,
    parse_year_range,
    range_years,
    source,
)

NEON_FLUX_PRODUCT = "DP4.00200.001"
CATALOG_ENDPOINTS = [
    "GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux",
    "GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET2015",
    "GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET-CH4",
]
CollectionArg = Literal["ameriflux", "fluxnet2015", "fluxnet_ch4", "all"]


# ---------------------------------------------------------------------- shared models


class ProductYears(AmfOutput):
    years: str | None = Field(None, description="Compact list, e.g. '1991-2012, 2014'.")
    count: int = Field(description="Number of years with published data.")
    first: int | None = None
    last: int | None = None


class TierInfo(AmfOutput):
    tier: Literal["CCBY4.0", "TIER2"] = Field(
        description="CCBY4.0 (Tier One) when CC-BY years exist, else TIER2 (Tier Two only)."
    )
    years: str | None = Field(None, description="Year range under that tier, e.g. '1991-2012'.")


class SiteProducts(AmfOutput):
    base: ProductYears | None = Field(None, description="AmeriFlux BASE-BADM years.")
    fluxnet: ProductYears | None = Field(None, description="AmeriFlux FLUXNET (FLUXNET-1F) years.")
    fluxnet2015: TierInfo | None = None
    fluxnet_ch4: TierInfo | None = None


def product_years(years: Sequence[int]) -> ProductYears | None:
    if not years:
        return None
    ordered = sorted(years)
    return ProductYears(
        years=compact_years(ordered), count=len(ordered), first=ordered[0], last=ordered[-1]
    )


def tier_info(tiers: TierYears | None) -> TierInfo | None:
    if tiers is None or (tiers.ccby is None and tiers.tier2 is None):
        return None
    if tiers.ccby:
        return TierInfo(tier="CCBY4.0", years=tiers.ccby)
    return TierInfo(tier="TIER2", years=tiers.tier2)


def site_products(record: SiteRecord) -> SiteProducts:
    return SiteProducts(
        base=product_years(record.base_years),
        fluxnet=product_years(record.fluxnet_years),
        fluxnet2015=tier_info(record.fluxnet2015),
        fluxnet_ch4=tier_info(record.fluxnet_ch4),
    )


def site_policy(record: SiteRecord) -> str | None:
    """AmeriFlux sites: their policy. FLUXNET-only sites: CCBY4.0 or TIER2 by tier years."""
    if record.policy:
        return record.policy
    for tiers in (record.fluxnet2015, record.fluxnet_ch4):
        if tiers is not None:
            return "TIER2" if tiers.tier2_only else "CCBY4.0"
    return None


async def site_index(ctx: ToolContext) -> SiteIndex:
    if ctx.catalog is None:  # pragma: no cover - every server builds a catalog
        raise ToolError("internal_error", "No site catalog is configured.")
    return await ctx.catalog.index(ctx.stats)


# ---------------------------------------------------------------------- amf_search_sites


class Near(AmfInput):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(100.0, gt=0, le=5000, description="Search radius in km.")


class SearchSitesIn(AmfInput):
    query: str | None = Field(
        None,
        max_length=200,
        description="Words matched against site ID, name, state, country, NEON code and "
        "networks (every word must match; prefixes count, e.g. 'harv').",
    )
    collection: CollectionArg = Field(
        "all",
        description="ameriflux (856 sites), fluxnet2015 (212), fluxnet_ch4 (81) or all.",
    )
    product: str | None = Field(
        None,
        description="Only sites with data in BASE-BADM, FLUXNET (FLUXNET-1F), FLUXNET2015 or "
        "FLUXNET-CH4.",
    )
    policy: str | None = Field(
        None,
        description="CCBY4.0, LEGACY (AmeriFlux) or TIER2 (Tier-Two-only FLUXNET2015/CH4 sites). "
        "CC-BY-4.0, Legacy and Tier2 spellings are accepted.",
    )
    igbp: list[str] | None = Field(
        None, max_length=17, description="IGBP classes, e.g. ['DBF', 'ENF'] (see the vocabulary)."
    )
    koeppen: list[str] | None = Field(
        None, max_length=30, description="Köppen codes or prefixes, e.g. ['Dfb'] or ['B']."
    )
    country: list[str] | None = Field(
        None,
        max_length=50,
        description="Country codes as in site IDs ('US', 'CA', 'BR') or names ('Canada').",
    )
    state: list[str] | None = Field(
        None, max_length=60, description="US state or province codes, e.g. ['NM', 'AZ']."
    )
    status: Literal["active", "inactive", "any"] = Field(
        "any", description="AmeriFlux tower status."
    )
    network: list[str] | None = Field(
        None,
        max_length=12,
        description="Member networks besides AmeriFlux, e.g. ['NEON'], ['LTER'], ['Phenocam'].",
    )
    bbox: list[float] | None = Field(
        None,
        min_length=4,
        max_length=4,
        description="[west, south, east, north] in decimal degrees (no antimeridian crossing).",
    )
    near: Near | None = Field(None, description="Sites within radius_km of a point.")
    years: str | None = Field(
        None,
        description="Data overlapping a year or range ('2015', '2010-2015') in the chosen product "
        "(default: BASE for AmeriFlux sites, the FLUXNET tier range otherwise).",
    )
    min_years: int | None = Field(None, ge=1, le=100, description="At least this many data years.")
    base_variable: list[str] | None = Field(
        None,
        max_length=20,
        description="FP Standard base names every site must measure, e.g. ['FCH4', 'SWC'].",
    )
    gas: list[str] | None = Field(
        None, max_length=6, description="Flux gas species, e.g. ['CH4'] or ['CO2', 'H2O']."
    )
    sort: Literal["site_id", "name", "years", "distance"] | None = Field(
        None, description="Default: distance with near, relevance with query, else site_id."
    )
    limit: int = Field(25, ge=1, le=200)
    offset: int = Field(0, ge=0)

    @field_validator("bbox")
    @classmethod
    def _bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        west, south, east, north = value
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError(
                "bbox must be [west, south, east, north] with west < east, south < north"
            )
        return value


class SiteSummary(AmfOutput):
    site_id: str
    name: str
    collections: list[str]
    country: str | None = None
    state: str | None = None
    igbp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    status: str | None = None
    policy: str | None = Field(None, description="CCBY4.0, LEGACY, or TIER2 (FLUXNET-only sites).")
    products: SiteProducts
    networks: list[str] = Field(default_factory=list)
    neon_site_code: str | None = None
    distance_km: float | None = None


class Facets(AmfOutput):
    collection: dict[str, int]
    igbp: dict[str, int]
    country: dict[str, int]
    policy: dict[str, int]
    status: dict[str, int]


class SearchSitesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "sites"
    sites: list[SiteSummary]
    facets: Facets = Field(description="Counts over every match, not just this page.")
    page: Page


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _vocab(record: SiteRecord) -> set[str]:
    out = set(words(record.site_id)) | set(words(record.name))
    out |= set(words(record.state)) | set(words(record.country))
    out |= {n.casefold() for n in record.networks}
    if record.neon_code:
        out.add(record.neon_code.casefold())
    out.add(record.site_id.casefold())
    return out


def _query_matches(tokens: list[str], record: SiteRecord) -> bool:
    import difflib

    vocab = _vocab(record)
    for token in tokens:
        if any(w.startswith(token) for w in vocab):
            continue
        if len(token) >= 4 and any(
            difflib.SequenceMatcher(None, token, w).ratio() >= 0.85 for w in vocab
        ):
            continue
        return False
    return True


def _has_product(record: SiteRecord, product: Product) -> bool:
    return {
        "BASE-BADM": bool(record.base_years),
        "FLUXNET": bool(record.fluxnet_years),
        "FLUXNET2015": record.fluxnet2015 is not None,
        "FLUXNET-CH4": record.fluxnet_ch4 is not None,
        "BIF": "ameriflux" in record.collections,
    }[product]


def _data_years(record: SiteRecord, product: Product | None) -> list[int]:
    if product == "FLUXNET":
        return list(record.fluxnet_years)
    if product in ("FLUXNET2015", "FLUXNET-CH4"):
        tiers = record.fluxnet2015 if product == "FLUXNET2015" else record.fluxnet_ch4
        return range_years(tiers.ccby or tiers.tier2) if tiers else []
    if record.base_years:
        return list(record.base_years)
    for tiers in (record.fluxnet2015, record.fluxnet_ch4):
        if tiers is not None:
            return range_years(tiers.ccby or tiers.tier2)
    return []


def _policy_matches(record: SiteRecord, product: Product | None, policy: Policy) -> bool:
    if product in ("FLUXNET2015", "FLUXNET-CH4"):
        tiers = record.fluxnet2015 if product == "FLUXNET2015" else record.fluxnet_ch4
        if tiers is None:
            return False
        return tiers.tier2_only if policy == "TIER2" else tiers.ccby is not None
    return site_policy(record) == policy


def _country_matches(record: SiteRecord, wanted: set[str]) -> bool:
    prefix = record.site_id.split("-", 1)[0].casefold()
    name = (record.country or "").casefold()
    return prefix in wanted or name in wanted or (name == "usa" and "united states" in wanted)


@register_tool(
    "amf_search_sites",
    title="Search AmeriFlux and FLUXNET sites",
    description=(
        "Find flux tower sites in the AmeriFlux (856), FLUXNET2015 (212) and FLUXNET-CH4 (81) "
        "catalogs by words, place (bbox or near a point), IGBP ecosystem, Köppen climate, "
        "country/state, status, member network (NEON, LTER, ...), data product and policy, years "
        "with data, measured variables or gas species. Returns compact site summaries with years "
        "per product, facets over all matches, and paging. Next: call amf_get_site for one site "
        "or amf_get_availability for exact years."
    ),
    input_model=SearchSitesIn,
    output_model=SearchSitesResult,
    surface="discovery",
    endpoints=CATALOG_ENDPOINTS,
)
async def amf_search_sites(args: SearchSitesIn, ctx: ToolContext) -> SearchSitesResult:
    product = normalize_product(args.product) if args.product else None
    policy = normalize_policy(args.policy) if args.policy else None
    if product == "BIF":
        raise ToolError(
            "invalid_argument",
            "BIF (BADM) membership is not part of the site catalog.",
            details={"field": "product", "input": args.product},
            hint="Use amf_get_availability(products=['BIF']) for BADM membership.",
        )
    if product and policy:
        validate(product, policy)
    window = parse_year_range(args.years)
    index = await site_index(ctx)
    notes: list[str] = []

    tokens = words(args.query) if args.query else []
    igbp = {c.casefold() for c in args.igbp or []}
    koeppen = [c.casefold() for c in args.koeppen or []]
    countries = {c.strip().casefold() for c in args.country or []}
    states = {s.strip().casefold() for s in args.state or []}
    networks = {n.strip().casefold() for n in args.network or []}
    variables = {v.strip().upper() for v in args.base_variable or []}
    gases = {g.strip().casefold() for g in args.gas or []}

    matched: list[tuple[SiteRecord, float | None]] = []
    for record in index.records.values():
        if args.collection != "all" and args.collection not in record.collections:
            continue
        if product and not _has_product(record, product):
            continue
        if policy and not _policy_matches(record, product, policy):
            continue
        if tokens and not _query_matches(tokens, record):
            continue
        if igbp and (record.igbp or "").casefold() not in igbp:
            continue
        if koeppen and not any((record.koeppen or "").casefold().startswith(k) for k in koeppen):
            continue
        if countries and not _country_matches(record, countries):
            continue
        if states and (record.state or "").casefold() not in states:
            continue
        if args.status != "any" and (record.status or "").casefold() != args.status:
            continue
        if networks and not networks <= {n.casefold() for n in record.networks}:
            continue
        if variables and not variables <= {v.upper() for v in record.base_variables}:
            continue
        if gases and not gases <= {g.casefold() for g in record.gas_species}:
            continue
        if args.bbox and not (
            record.latitude is not None
            and record.longitude is not None
            and args.bbox[0] <= record.longitude <= args.bbox[2]
            and args.bbox[1] <= record.latitude <= args.bbox[3]
        ):
            continue
        distance: float | None = None
        if args.near:
            if record.latitude is None or record.longitude is None:
                continue
            distance = _haversine_km(
                args.near.latitude, args.near.longitude, record.latitude, record.longitude
            )
            if distance > args.near.radius_km:
                continue
        if window or args.min_years:
            years = _data_years(record, product)
            if window and not any(window[0] <= y <= window[1] for y in years):
                continue
            if args.min_years and len(years) < args.min_years:
                continue
        matched.append((record, distance))

    sort = args.sort or ("distance" if args.near else "relevance" if tokens else "site_id")
    if sort == "distance":
        if not args.near:
            raise ToolError(
                "invalid_argument",
                "sort='distance' needs near.",
                details={"field": "sort"},
            )
        matched.sort(key=lambda m: (m[1] if m[1] is not None else math.inf, m[0].site_id))
    elif sort == "relevance":
        query = args.query or ""
        matched.sort(key=lambda m: (-name_score(query, m[0].name), m[0].site_id))
    elif sort == "name":
        matched.sort(key=lambda m: (m[0].name.casefold(), m[0].site_id))
    elif sort == "years":
        matched.sort(key=lambda m: (-len(_data_years(m[0], product)), m[0].site_id))
    else:
        matched.sort(key=lambda m: m[0].site_id)

    def count(values: Sequence[str | None]) -> dict[str, int]:
        return dict(Counter(v or "unknown" for v in values).most_common())

    facets = Facets(
        collection=count([c for r, _ in matched for c in sorted(r.collections)]),
        igbp=count([r.igbp for r, _ in matched]),
        country=count([r.country for r, _ in matched]),
        policy=count([site_policy(r) for r, _ in matched]),
        status=count([r.status for r, _ in matched]),
    )
    page_items, page = paginate(matched, offset=args.offset, limit=args.limit)
    sites = [
        SiteSummary(
            site_id=r.site_id,
            name=r.name,
            collections=sorted(r.collections),
            country=r.country,
            state=r.state,
            igbp=r.igbp,
            latitude=r.latitude,
            longitude=r.longitude,
            elevation_m=r.elevation_m,
            status=r.status,
            policy=site_policy(r),
            products=site_products(r),
            networks=[n for n in r.networks if n != "AmeriFlux"],
            neon_site_code=r.neon_code,
            distance_km=round(d, 1) if d is not None else None,
        )
        for r, d in page_items
    ]
    if not matched:
        notes.append("No site matches every filter; drop a filter or widen the area or years.")
    steps = []
    if sites:
        first = sites[0].site_id
        steps.append(f"amf_get_site(site='{first}') for details, team and links")
        steps.append(f"amf_get_availability(sites=['{first}']) for exact years per product")
    if page.next_offset is not None:
        steps.append(f"amf_search_sites(..., offset={page.next_offset}) for the next page")
    return SearchSitesResult(
        sites=sites,
        facets=facets,
        page=page,
        notes=notes,
        next_steps=steps,
        source=source(ctx),
    )


# ---------------------------------------------------------------------- amf_get_site

SiteSection = Literal["description", "team", "variables", "disturbance"]


class GetSiteIn(AmfInput):
    site: str = Field(
        max_length=200,
        description="Site ID (US-Ha1, any case), NEON code (SRER), FLUXNET2015 old ID (DK-ZaF) "
        "or site name.",
    )
    include: list[SiteSection] | None = Field(
        None,
        description="Optional sections; default all: description, team, variables, disturbance.",
    )
    include_contacts: bool = Field(
        False,
        description="Include team emails, if the server allows it (privacy.allow_contact_emails).",
    )


class Location(AmfOutput):
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    country: str | None = None
    state: str | None = None


class Ecosystem(AmfOutput):
    igbp: str | None = None
    igbp_label: str | None = Field(None, description="AmeriFlux's description of the IGBP class.")
    koeppen: str | None = None
    koeppen_label: str | None = None
    koeppen_note: str | None = Field(
        None, description="Where AmeriFlux's Köppen wording departs from the standard."
    )
    mat_c: float | None = Field(None, description="Mean annual temperature (deg C).")
    map_mm: float | None = Field(None, description="Mean annual precipitation (mm).")


class PolicyInfo(AmfOutput):
    code: str | None
    meaning: str


class Dois(AmfOutput):
    base: str | None = Field(None, description="AmeriFlux BASE-BADM DOI (also used for BADM).")
    fluxnet: str | None = Field(None, description="AmeriFlux FLUXNET (FLUXNET-1F) DOI.")


class Tower(AmfOutput):
    start: str | None = None
    end: str | None = None


class TeamEntry(AmfOutput):
    name: str
    role: str | None = None
    institution: str | None = None
    email: str | None = None


class LterLink(AmfOutput):
    lter_site: str | None = None
    edi_scope: str | None = None
    basis: str
    note: str | None = None
    status: Literal["draft"] = "draft"


class Crosslinks(AmfOutput):
    neon_site_code: str | None = None
    neon_data_product: str | None = Field(
        None, description="NEON's bundled eddy-covariance product for the same tower."
    )
    lter: LterLink | None = None
    ameriflux_page: str | None = None
    fluxnet_page: str | None = None
    site_url: str | None = None


class GetSiteResult(ToolResultBase):
    site_id: str
    name: str
    collections: list[str]
    status: str | None = None
    tower: Tower
    location: Location
    ecosystem: Ecosystem
    policy: PolicyInfo
    dois: Dois
    products: SiteProducts
    networks: list[str]
    crosslinks: Crosslinks
    gas_species: list[str] = Field(default_factory=list)
    description: str | None = None
    disturbance: list[str] | None = None
    team: list[TeamEntry] | None = None
    team_total: int | None = None
    base_variables: list[str] | None = Field(
        None, description="FP Standard base names in the site's BASE data (up to 60)."
    )
    base_variables_total: int | None = None


_POLICY_MEANINGS: dict[str, str] = {
    "CCBY4.0": "CC-BY-4.0: cite the site's DOI and acknowledge DOE funding; combining with Legacy "
    "data means following the Legacy policy.",
    "LEGACY": "AmeriFlux Legacy: contact the site PIs when you start in-depth analysis, cite the "
    "DOI, acknowledge site and DOE funding, inform the PIs before publication. No FLUXNET product.",
    "TIER2": "FLUXNET Tier Two: scientific and educational use; give the data providers three "
    "weeks after the first draft. Mixing with Tier One data means Tier Two applies.",
}
MAX_TEAM = 20
MAX_VARIABLES = 60
MAX_DESCRIPTION = 1200


@register_tool(
    "amf_get_site",
    title="Get one AmeriFlux or FLUXNET site",
    description=(
        "One site by ID (any case), NEON code, FLUXNET2015 old ID or name: location, IGBP and "
        "Köppen with AmeriFlux's descriptions, data policy and what it means, DOIs, years per "
        "product (BASE, FLUXNET, FLUXNET2015, FLUXNET-CH4), member networks, links to NEON and "
        "to LTER data in EDI, team (no emails by default), measured BASE variables. Next: call "
        "amf_get_availability for exact years or amf_get_citation to cite it."
    ),
    input_model=GetSiteIn,
    output_model=GetSiteResult,
    surface="discovery",
    endpoints=CATALOG_ENDPOINTS,
)
async def amf_get_site(args: GetSiteIn, ctx: ToolContext) -> GetSiteResult:
    index = await site_index(ctx)
    resolution = resolve_site(args.site, index)
    record = resolution.record
    sections = set(args.include or ("description", "team", "variables", "disturbance"))
    notes = list(resolution.notes)

    policy_code = site_policy(record)
    team: list[TeamEntry] | None = None
    if "team" in sections:
        show_email = contacts_allowed(ctx.config, args.include_contacts)
        team = [
            TeamEntry(
                name=m.name,
                role=m.role,
                institution=m.institution,
                email=m.email if show_email else None,
            )
            for m in record.team[:MAX_TEAM]
        ]
        if args.include_contacts and not show_email:
            notes.append(CONTACTS_WITHHELD_NOTE)
        elif show_email and record.team and not any(m.email for m in record.team):
            notes.append("Contact emails are unavailable: the catalog was loaded from disk cache.")
    description = record.description if "description" in sections else None
    if description and len(description) > MAX_DESCRIPTION:
        description = description[:MAX_DESCRIPTION].rstrip() + "…"
    lter_row = lter_link(record.site_id)
    crosslinks = Crosslinks(
        neon_site_code=record.neon_code,
        neon_data_product=NEON_FLUX_PRODUCT if record.neon_code else None,
        lter=LterLink(
            lter_site=lter_row.get("lterSite"),
            edi_scope=lter_row.get("ediScope"),
            basis=lter_row["basis"],
            note=lter_row.get("note"),
        )
        if lter_row
        else None,
        ameriflux_page=record.url_ameriflux,
        fluxnet_page=record.url_fluxnet,
        site_url=record.url,
    )
    if "ameriflux" not in record.collections:
        notes.append(
            f"{record.site_id} is not an AmeriFlux site: only FLUXNET catalog fields are known."
        )
    if policy_code == "LEGACY":
        notes.append(
            "Legacy policy: contact the PIs before in-depth analysis; there is no FLUXNET product."
        )

    steps = [f"amf_get_availability(sites=['{record.site_id}']) for exact years per product"]
    if record.neon_code:
        steps.append(
            f"neon_get_availability(product='{NEON_FLUX_PRODUCT}', site='{record.neon_code}') "
            "on the NEON MCP server for NEON's own flux bundle"
        )
    if lter_row and lter_row.get("ediScope"):
        steps.append(
            f"edi_search_packages(scope='{lter_row['ediScope']}') on the EDI MCP server for LTER "
            "data from the same site"
        )
    return GetSiteResult(
        site_id=record.site_id,
        name=record.name,
        collections=sorted(record.collections),
        status=record.status,
        tower=Tower(start=record.tower_start, end=record.tower_end),
        location=Location(
            latitude=record.latitude,
            longitude=record.longitude,
            elevation_m=record.elevation_m,
            country=record.country,
            state=record.state,
        ),
        ecosystem=Ecosystem(
            igbp=record.igbp,
            igbp_label=igbp_label(record.igbp),
            koeppen=record.koeppen,
            koeppen_label=koeppen_label(record.koeppen),
            koeppen_note=koeppen_caveat(record.koeppen),
            mat_c=record.mat_c,
            map_mm=record.map_mm,
        ),
        policy=PolicyInfo(
            code=policy_code,
            meaning=_POLICY_MEANINGS.get(policy_code or "", "No data policy is recorded."),
        ),
        dois=Dois(base=record.dois.get("AmeriFlux"), fluxnet=record.dois.get("FLUXNET")),
        products=site_products(record),
        networks=list(record.networks),
        crosslinks=crosslinks,
        gas_species=list(record.gas_species),
        description=description,
        disturbance=list(record.disturbance) if "disturbance" in sections else None,
        team=team,
        team_total=len(record.team) if team is not None else None,
        base_variables=list(record.base_variables[:MAX_VARIABLES])
        if "variables" in sections
        else None,
        base_variables_total=len(record.base_variables) if "variables" in sections else None,
        resolved=[resolution.resolved] if resolution.resolved else [],
        notes=notes,
        next_steps=steps,
        source=source(ctx),
    )
