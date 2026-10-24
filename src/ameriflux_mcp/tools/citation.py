"""Citation: ``amf_get_citation`` (build step 5)."""

from __future__ import annotations

import asyncio
from typing import ClassVar, Literal

from pydantic import Field

from ameriflux_mcp.ameriflux import acknowledgments as ack
from ameriflux_mcp.ameriflux.catalog import SiteRecord
from ameriflux_mcp.ameriflux.citation import (
    CATALOG_DOI_KEYS,
    DOI_SEGMENTS,
    CitationProduct,
    SiteCitation,
    bibtex,
    datacite_citation,
    doi_record,
    from_doi_record,
)
from ameriflux_mcp.ameriflux.policy import effective_policy
from ameriflux_mcp.ameriflux.products import normalize_product
from ameriflux_mcp.ameriflux.resolve import resolve_sites
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import AmeriFluxApiError, ToolError, map_api_error
from ameriflux_mcp.logging import registered_secrets
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Page, ToolResultBase
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import merge_notes, paginate, source
from ameriflux_mcp.tools.availability import ObligationOut
from ameriflux_mcp.tools.sites import site_index

CITATION_ENDPOINTS = ["GET amfcdn.lbl.gov/api/v1/DOI/{site}/{product}"]
BIF_NOTE = (
    "BADM (BIF) has no DOI of its own: it is cited with the site's BASE-BADM DOI, which "
    "AmeriFlux publishes with the BADM."
)


class CitationIn(AmfInput):
    sites: list[str] = Field(
        min_length=1,
        max_length=50,
        description="Site IDs (any case), NEON codes, FLUXNET2015 old IDs or names.",
    )
    product: str = Field(
        "BASE-BADM",
        description="BASE-BADM, BIF (cited with the BASE DOI), FLUXNET (FLUXNET-1F) or "
        "FLUXNET2015. FLUXNET-CH4 citations arrive in v0.2.",
    )
    include_bibtex: bool = Field(False, description="Add a BibTeX @misc entry per citation.")


class CitationOut(AmfOutput):
    site_id: str
    product: str
    doi: str
    citation: str = Field(description="Cite in the reference list, as written.")
    source: Literal["amfcdn", "constructed", "datacite"] = Field(
        description="amfcdn: AmeriFlux's own text; constructed: built from the DOI record as the "
        "FLUXNET DOI page shows it; datacite: fallback without a product version."
    )
    version: str | None = Field(
        None, description="Product version, e.g. 28-5 or v1.3_r1 (1991-2025)."
    )
    year: str | None = None
    policy: str | None = Field(None, description="The data policy in the site's DOI record.")
    title: str | None = None
    site_page: str | None = None
    bibtex: str | None = None
    warnings: list[str] = Field(default_factory=list)


class MissingCitation(AmfOutput):
    site_id: str
    reason: str


class EffectivePolicyOut(AmfOutput):
    collection: str
    code: str
    reason: str
    obligations: list[ObligationOut]


class AcknowledgmentOut(AmfOutput):
    key: str
    text: str = Field(description="Verbatim from the data-policy page.")
    applies_to: str


class SiteFunding(AmfOutput):
    site_id: str
    sponsors: list[str]


class DataAvailabilityOut(AmfOutput):
    statement: str = Field(description="Verbatim template; fill in [SOURCE] and the date.")
    source_options: list[str]


class ReferenceOut(AmfOutput):
    key: str
    text: str
    applies_to: str


class CitationResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "citations"
    budget_elide_fields: ClassVar[tuple[str, ...]] = ("bibtex",)
    budget_elide_flag: ClassVar[str | None] = "bibtex_elided"
    budget_next_step: ClassVar[str | None] = (
        "amf_get_citation(sites=[...]) for the sites after position {next_offset}"
    )
    product: str
    citations: list[CitationOut]
    missing: list[MissingCitation] = Field(
        default_factory=list, description="Requested sites without a citation, and why."
    )
    effective_policy: EffectivePolicyOut
    acknowledgments: list[AcknowledgmentOut]
    site_funding: list[SiteFunding] = Field(
        default_factory=list,
        description="Legacy policy: acknowledge each site's funding (DOI record sponsors).",
    )
    data_availability: DataAvailabilityOut | None = None
    processing_references: list[ReferenceOut]
    bibtex_elided: bool | None = None
    page: Page


def _has_product(record: SiteRecord, product: CitationProduct) -> str | None:
    """Why ``record`` has no citation for ``product`` (None when it should have one)."""
    if product in ("BASE-BADM", "BIF"):
        if "ameriflux" not in record.collections:
            return "is not an AmeriFlux site"
        if not record.base_years and "AmeriFlux" not in record.dois:
            return "has no published BASE-BADM data"
    elif product == "FLUXNET":
        if "ameriflux" not in record.collections:
            return "is not an AmeriFlux site"
        if not record.fluxnet_years and "FLUXNET" not in record.dois:
            return "has no AmeriFlux FLUXNET product"
    elif record.fluxnet2015 is None:
        return "is not part of FLUXNET2015"
    return None


def _fallback_allowed(exc: AmeriFluxApiError) -> bool:
    return exc.kind in ("transport", "drift", "decode") or exc.status >= 500


async def _cite_one(
    ctx: ToolContext, record: SiteRecord, product: CitationProduct
) -> SiteCitation | str:
    segment = DOI_SEGMENTS[product]
    try:
        doi = await doi_record(ctx, record.site_id, segment)
    except AmeriFluxApiError as exc:
        catalog_doi = record.dois.get(CATALOG_DOI_KEYS.get(segment, ""))
        if not (_fallback_allowed(exc) and catalog_doi):
            raise
        return await datacite_citation(ctx, record, product, catalog_doi)
    if doi is None:
        return f"the AmeriFlux DOI API has no {segment} record for this site"
    return from_doi_record(record, product, doi)


def _acknowledgments(product: CitationProduct, code: str) -> list[AcknowledgmentOut]:
    texts: list[ack.Text] = []
    if product != "FLUXNET2015":
        texts.append(ack.DOE_DATA_PORTAL if code == "LEGACY" else ack.DOE_DATA_SERVICE)
    if product == "FLUXNET":
        texts.append(ack.FLUXNET_NETWORKS)
    return [AcknowledgmentOut(key=t.key, text=t.text, applies_to=t.applies_to) for t in texts]


@register_tool(
    "amf_get_citation",
    title="Get citations and acknowledgments for sites",
    description=(
        "Citations for up to 50 sites and one product (BASE-BADM, BIF, FLUXNET, FLUXNET2015): "
        "AmeriFlux's own versioned text per site DOI (e.g. 'Ver. 28-5'), the policy the "
        "selection must follow with its obligations (mixing CC-BY and Legacy means Legacy; "
        "mixing tiers means Tier Two), verbatim acknowledgments, Legacy site funding, the "
        "data-availability sentence and processing papers. Optional BibTeX. Next: cite every "
        "site in the reference list and follow the obligations."
    ),
    input_model=CitationIn,
    output_model=CitationResult,
    surface="citation",
    endpoints=CITATION_ENDPOINTS,
)
async def amf_get_citation(args: CitationIn, ctx: ToolContext) -> CitationResult:
    product = normalize_product(args.product)
    if product == "FLUXNET-CH4":
        raise ToolError(
            "feature_unavailable",
            "FLUXNET-CH4 citations are planned for v0.2 (the product reference is unconfirmed).",
            details={"product": product, "reason": "fluxnet_ch4_citation"},
            hint="amf_get_site gives the site; the FLUXNET-CH4 policy is in amf_get_availability.",
        )
    cite_product: CitationProduct = product
    index = await site_index(ctx)
    resolutions = resolve_sites(args.sites, index)
    records = [r.record for r in resolutions]
    notes: list[str] = [n for r in resolutions for n in r.notes]
    policy = effective_policy(product, records)

    missing: list[MissingCitation] = []
    eligible: list[SiteRecord] = []
    for record in records:
        reason = policy.ineligible.get(record.site_id) or _has_product(record, cite_product)
        if reason:
            missing.append(
                MissingCitation(site_id=record.site_id, reason=f"{record.site_id} {reason}")
            )
        else:
            eligible.append(record)

    outcomes = await asyncio.gather(
        *(_cite_one(ctx, record, cite_product) for record in eligible), return_exceptions=True
    )
    citations: list[SiteCitation] = []
    failures: list[AmeriFluxApiError] = []
    for record, outcome in zip(eligible, outcomes, strict=True):
        if isinstance(outcome, AmeriFluxApiError):
            failures.append(outcome)
            missing.append(
                MissingCitation(
                    site_id=record.site_id,
                    reason=f"{record.site_id}: the DOI service failed ({outcome.status or outcome.kind})",
                )
            )
        elif isinstance(outcome, BaseException):
            raise outcome
        elif isinstance(outcome, str):
            missing.append(
                MissingCitation(site_id=record.site_id, reason=f"{record.site_id}: {outcome}")
            )
        else:
            citations.append(outcome)
    if failures and not citations:
        raise map_api_error(failures[0], secrets=registered_secrets())

    if cite_product == "BIF":
        notes.append(BIF_NOTE)
    if any(c.source == "constructed" for c in citations):
        notes.append(
            "FLUXNET2015 citations are built from the DOI record the way the FLUXNET DOI page "
            "shows them (authors, Tier Two years, title, DOI); AmeriFlux publishes no text."
        )
    if any(c.source == "datacite" for c in citations):
        notes.append("Some citations come from DataCite because the AmeriFlux DOI API failed.")
    for c in citations:
        if c.policy and c.policy != "CCBY4.0" and policy.code == "CCBY4.0":
            notes.append(f"{c.site_id}'s DOI record lists {c.policy}; check its data policy.")

    site_funding: list[SiteFunding] = []
    if policy.code == "LEGACY":
        site_funding = [
            SiteFunding(site_id=c.site_id, sponsors=c.sponsors) for c in citations if c.sponsors
        ]
        without = [c.site_id for c in citations if not c.sponsors]
        if without:
            notes.append(
                f"No sponsor in the DOI record of {', '.join(without)}: take the funding text "
                "from the site's BADM (GRP_ACKNOWLEDGEMENT in the BIF file)."
            )

    out = [
        CitationOut(
            site_id=c.site_id,
            product=c.product,
            doi=c.doi,
            citation=c.text,
            source=c.source,
            version=c.version,
            year=c.year,
            policy=c.policy,
            title=c.title,
            site_page=c.site_page,
            bibtex=bibtex(c) if args.include_bibtex else None,
            warnings=c.warnings,
        )
        for c in citations
    ]
    page_items, page = paginate(out, offset=0, limit=max(len(out), 1))
    data_availability = None
    if cite_product in ack.DATA_PRODUCT_NAMES:
        data_availability = DataAvailabilityOut(
            statement=ack.DATA_AVAILABILITY.text.replace(
                "[DATA PRODUCT]", ack.DATA_PRODUCT_NAMES[cite_product]
            ),
            source_options=list(ack.DATA_SOURCES),
        )
    steps = []
    if missing:
        steps.append(
            "amf_get_availability(sites=[...]) to see which products the missing sites have"
        )
    if cite_product in ("BASE-BADM", "FLUXNET") and policy.code == "CCBY4.0":
        steps.append(
            f"amf_get_citation(sites=[...], product='{'FLUXNET' if cite_product == 'BASE-BADM' else 'BASE-BADM'}') "
            "if you also use the other AmeriFlux product"
        )
    return CitationResult(
        product=cite_product,
        citations=page_items,
        missing=missing,
        effective_policy=EffectivePolicyOut(
            collection=policy.collection,
            code=policy.code,
            reason=policy.reason,
            obligations=[ObligationOut(text=o.text, level=o.level) for o in policy.obligations],
        ),
        acknowledgments=_acknowledgments(cite_product, policy.code),
        site_funding=site_funding,
        data_availability=data_availability,
        processing_references=[
            ReferenceOut(key=r.key, text=r.text, applies_to=r.applies_to)
            for r in ack.processing_references(cite_product)
        ],
        page=page,
        resolved=[r.resolved for r in resolutions if r.resolved],
        notes=merge_notes(notes),
        next_steps=steps,
        source=source(ctx, derived=["effectivePolicy", "acknowledgments", "bibtex"]),
    )


__all__ = ["amf_get_citation"]
