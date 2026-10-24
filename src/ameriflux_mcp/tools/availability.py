"""``amf_get_availability``: published years per site, product and policy (build step 4).

Sources (DESIGN.md D6, D7): ``v1/data_availability/{network}/{product}/{policy}`` for
BASE-BADM, FLUXNET, FLUXNET2015 and FLUXNET-CH4, and ``v1/site_availability`` for BIF
membership (its data_availability rows are always empty). Every product/policy pair
is validated before any request, because the AmeriFlux network answers an invalid one
with 200 and empty rows (E42).

Without a ``policy`` both lists are read and each row is labelled with the policy the
site's data actually carry: LEGACY (and TIER2) lists are supersets of the CC-BY lists
(E15), so nothing is lost and a CC-BY site is never mislabelled.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from ameriflux_mcp.ameriflux.catalog import SiteRecord
from ameriflux_mcp.ameriflux.client import AmeriFluxClient
from ameriflux_mcp.ameriflux.endpoints import DATA_AVAILABILITY, SITE_AVAILABILITY
from ameriflux_mcp.ameriflux.policy import effective_policy, union
from ameriflux_mcp.ameriflux.products import (
    Policy,
    Product,
    info,
    normalize_policy,
    normalize_product,
    validate,
)
from ameriflux_mcp.ameriflux.resolve import resolve_sites
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Page, ToolResultBase
from ameriflux_mcp.models.upstream import AvailabilityRow as UpstreamRow
from ameriflux_mcp.models.upstream import parse_rows
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import compact_years, paginate, parse_year_range, source
from ameriflux_mcp.tools.sites import site_index

AVAILABILITY_ENDPOINTS = [
    "GET amfcdn.lbl.gov/api/v1/data_availability/{network}/{product}/{policy}",
    "GET amfcdn.lbl.gov/api/v1/site_availability",
    "GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux",
]
#: Products read per collection when none are given.
DEFAULT_PRODUCTS: dict[str, tuple[Product, ...]] = {
    "ameriflux": ("BASE-BADM", "FLUXNET"),
    "fluxnet2015": ("FLUXNET2015",),
    "fluxnet_ch4": ("FLUXNET-CH4",),
}
MAX_SITES = 50


class AvailabilityIn(AmfInput):
    sites: list[str] | None = Field(
        None,
        max_length=MAX_SITES,
        description="Site IDs, NEON codes or names (up to 50). Omit for every site with data.",
    )
    products: list[str] | None = Field(
        None,
        max_length=5,
        description="BASE-BADM, BIF, FLUXNET, FLUXNET2015, FLUXNET-CH4. Default: the products of "
        "each site's collections (BASE-BADM and FLUXNET for AmeriFlux sites), or BASE-BADM when "
        "no sites are given.",
    )
    policy: str | None = Field(
        None,
        description="CCBY4.0, LEGACY or TIER2: only data usable under that policy. Default: every "
        "row labelled with its own policy.",
    )
    years: str | None = Field(None, description="Only years in this window: '2015' or '2010-2015'.")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class AvailabilityRow(AmfOutput):
    site_id: str
    product: str
    policy: str = Field(description="The policy these years are shared under.")
    years: str | None = Field(None, description="Compact list, e.g. '1991-2012, 2014'.")
    count: int | None = None
    first: int | None = None
    last: int | None = None
    membership: bool | None = Field(
        None, description="BIF only: the site has BADM in the bulk files (no years are published)."
    )


class EmptySite(AmfOutput):
    site_id: str
    product: str
    reason: str


class ObligationOut(AmfOutput):
    text: str
    level: Literal["required", "recommended"]


class PolicyVerdict(AmfOutput):
    collection: str
    product: str
    code: str
    reason: str
    obligations: list[ObligationOut]


class AvailabilitySummary(AmfOutput):
    rows: int
    sites_with_data: int
    by_product: dict[str, int]


class AvailabilityResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "rows"
    rows: list[AvailabilityRow]
    empty_sites: list[EmptySite] = Field(
        default_factory=list, description="Requested sites without data for a product, and why."
    )
    policy_verdict: list[PolicyVerdict] = Field(
        default_factory=list,
        description="The policy the requested sites must follow, per product, with obligations.",
    )
    combined_obligations: list[ObligationOut] = Field(
        default_factory=list, description="Every obligation once, across all collections."
    )
    summary: AvailabilitySummary
    page: Page


def _policies_to_read(product: Product, policy: Policy | None) -> tuple[Policy, ...]:
    if policy is not None:
        validate(product, policy)
        return (policy,)
    return info(product).policies


def _client(ctx: ToolContext) -> AmeriFluxClient:
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise ToolError("internal_error", "No upstream client is configured.")
    return ctx.client


async def _read_years(ctx: ToolContext, product: Product, policy: Policy) -> dict[str, list[int]]:
    network = info(product).network
    rows = await _client(ctx).fetch(
        DATA_AVAILABILITY, stats=ctx.stats, network=network, product=product, policy=policy
    )
    parsed = parse_rows(UpstreamRow, rows, endpoint=DATA_AVAILABILITY.name)
    return {r.SITE_ID: sorted(r.publish_years) for r in parsed if r.publish_years}


async def _read_bif(ctx: ToolContext) -> dict[str, set[str]]:
    tree: dict[str, Any] = await _client(ctx).fetch(SITE_AVAILABILITY, stats=ctx.stats)
    bif = (tree.get("AmeriFlux") or {}).get("BIF") or {}
    return {
        policy: {pair[0] for pair in pairs if pair}
        for policy, pairs in bif.items()
        if isinstance(pairs, list)
    }


def _empty_reason(record: SiteRecord | None, product: Product, policy: Policy | None) -> str:
    if record is None:
        return "no published data"
    collection = info(product).collection
    if collection not in record.collections:
        return f"not part of {info(product).label}"
    if product == "FLUXNET" and record.policy == "LEGACY":
        return "shares its data under the Legacy policy; the FLUXNET product is CC-BY-4.0 only"
    if policy == "CCBY4.0" and record.policy == "LEGACY":
        return "shares its data under the Legacy policy, not CC-BY-4.0"
    tiers = record.fluxnet2015 if product == "FLUXNET2015" else record.fluxnet_ch4
    if policy == "CCBY4.0" and tiers is not None and tiers.tier2_only:
        return "Tier Two only; no CC-BY-4.0 (Tier One) years"
    return "no published years"


@register_tool(
    "amf_get_availability",
    title="Get data availability per site and product",
    description=(
        "Published years per site for AmeriFlux BASE-BADM and FLUXNET (FLUXNET-1F), FLUXNET2015 "
        "and FLUXNET-CH4, and BADM (BIF) membership, each labelled with the data policy it is "
        "shared under (CC-BY-4.0, Legacy, Tier Two). Lists requested sites without data and why, "
        "and the policy the selection must follow with its obligations. Invalid product/policy "
        "pairs fail before any request. Next: call amf_get_citation for these sites."
    ),
    input_model=AvailabilityIn,
    output_model=AvailabilityResult,
    surface="availability",
    endpoints=AVAILABILITY_ENDPOINTS,
)
async def amf_get_availability(args: AvailabilityIn, ctx: ToolContext) -> AvailabilityResult:
    policy = normalize_policy(args.policy) if args.policy else None
    requested_products = [normalize_product(p, field="products") for p in args.products or []]
    window = parse_year_range(args.years)
    # Validate every pair before any request (D6).
    for product in requested_products:
        _policies_to_read(product, policy)

    notes: list[str] = []
    resolved = []
    records: list[SiteRecord] = []
    index = await site_index(ctx)
    if args.sites:
        resolutions = resolve_sites(args.sites, index)
        records = [r.record for r in resolutions]
        resolved = [r.resolved for r in resolutions if r.resolved]
        for r in resolutions:
            notes.extend(r.notes)
    if requested_products:
        products = list(dict.fromkeys(requested_products))
    elif records:
        products = list(
            dict.fromkeys(
                p
                for rec in records
                for collection in sorted(rec.collections)
                for p in DEFAULT_PRODUCTS[collection]
            )
        )
    else:
        products = ["BASE-BADM"]
    if policy is not None:
        products = [p for p in products if policy in info(p).policies]
        if not products:
            raise ToolError(
                "invalid_argument",
                f"None of these sites' products has {policy} data.",
                details={"reason": "invalid_combination", "policy": policy},
                hint="TIER2 applies to FLUXNET2015 and FLUXNET-CH4; LEGACY to BASE-BADM and BIF.",
            )

    wanted = {r.site_id for r in records} if records else None
    rows: list[AvailabilityRow] = []
    empty: list[EmptySite] = []
    with_data: dict[str, set[str]] = {}

    for product in products:
        policies = _policies_to_read(product, policy)
        found: dict[str, tuple[Policy, list[int] | None]] = {}
        if product == "BIF":
            members = await _read_bif(ctx)
            ccby = members.get("CCBY4.0", set())
            for pol in policies:
                for site_id in members.get(pol, set()):
                    if wanted is None or site_id in wanted:
                        label: Policy = "CCBY4.0" if site_id in ccby else pol
                        found.setdefault(site_id, (label, None))
        else:
            lists = {pol: await _read_years(ctx, product, pol) for pol in policies}
            ccby_list = lists.get("CCBY4.0", {})
            superset_policy: Policy = policies[-1]
            for site_id, years in lists[superset_policy].items():
                if wanted is not None and site_id not in wanted:
                    continue
                label = "CCBY4.0" if site_id in ccby_list else superset_policy
                if window:
                    years = [y for y in years if window[0] <= y <= window[1]]
                if years:
                    found[site_id] = (label, years)
        for site_id in sorted(found):
            label, site_years = found[site_id]
            with_data.setdefault(product, set()).add(site_id)
            if site_years is None:
                rows.append(
                    AvailabilityRow(site_id=site_id, product=product, policy=label, membership=True)
                )
            else:
                rows.append(
                    AvailabilityRow(
                        site_id=site_id,
                        product=product,
                        policy=label,
                        years=compact_years(site_years),
                        count=len(site_years),
                        first=site_years[0],
                        last=site_years[-1],
                    )
                )
        if records:
            for rec in records:
                if rec.site_id in found:
                    continue
                reason = _empty_reason(rec, product, policy)
                if not requested_products and reason.startswith("not part of"):
                    continue  # defaulted products: a site outside the collection is no news
                if window and reason == "no published years":
                    reason = f"no data in {args.years}"
                empty.append(EmptySite(site_id=rec.site_id, product=product, reason=reason))

    verdicts: list[PolicyVerdict] = []
    if records:
        effective = []
        for product in products:
            selected = [r for r in records if r.site_id in with_data.get(product, set())]
            if not selected:
                continue
            verdict = effective_policy(product, selected, policy)
            effective.append(verdict)
            verdicts.append(
                PolicyVerdict(
                    collection=verdict.collection,
                    product=product,
                    code=verdict.code,
                    reason=verdict.reason,
                    obligations=[
                        ObligationOut(text=o.text, level=o.level) for o in verdict.obligations
                    ],
                )
            )
        combined = [ObligationOut(text=o.text, level=o.level) for o in union(effective)]
    else:
        combined = []
        notes.append(
            "No sites were given, so no policy verdict: pass sites to see the policy and "
            "obligations a selection must follow."
        )
    if "FLUXNET" in products and any(r.policy == "LEGACY" for r in records):
        notes.append("The AmeriFlux FLUXNET product exists only for CC-BY-4.0 sites.")
    if "BIF" in products:
        notes.append(
            "BIF availability is membership only (no years); BADM for one site also comes "
            "inside its BASE-BADM download."
        )

    page_rows, page = paginate(rows, offset=args.offset, limit=args.limit)
    summary = AvailabilitySummary(
        rows=len(rows),
        sites_with_data=len(set().union(*with_data.values())) if with_data else 0,
        by_product={p: len(with_data.get(p, set())) for p in products},
    )
    steps = []
    cited = sorted(set().union(*with_data.values()))[:5] if with_data else []
    if cited:
        steps.append(f"amf_get_citation(sites={cited!r}, product='{products[0]}') to cite them")
    if page.next_offset is not None:
        steps.append(f"amf_get_availability(..., offset={page.next_offset}) for more rows")
    return AvailabilityResult(
        rows=page_rows,
        empty_sites=empty,
        policy_verdict=verdicts,
        combined_obligations=combined,
        summary=summary,
        page=page,
        resolved=list(resolved),
        notes=list(dict.fromkeys(notes)),
        next_steps=steps,
        source=source(ctx),
    )
