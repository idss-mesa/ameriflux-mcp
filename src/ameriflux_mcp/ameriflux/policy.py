"""The data-policy engine (DESIGN.md D10).

Each selection of sites has one effective policy per collection:

* **AmeriFlux** (BASE-BADM, BIF, FLUXNET): LEGACY when LEGACY is requested or any
  selected site shares its data under the Legacy policy, else CCBY4.0. Mixing CC-BY
  and Legacy data means following Legacy for everything (E24). The FLUXNET product
  exists only for CC-BY sites, so Legacy sites are *ineligible* for it and asking for
  FLUXNET under LEGACY is ``invalid_argument`` (``fluxnet_requires_ccby``).
* **FLUXNET2015 / FLUXNET-CH4**: TIER2 when TIER2 is requested or any selected site
  is Tier-2-only, else CCBY4.0 (mixing tiers means Tier Two, E26).

Obligations come with each policy, marked ``required`` or ``recommended``; a
selection that spans collections gets the union, one block per collection.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from ameriflux_mcp.ameriflux.catalog import SiteRecord
from ameriflux_mcp.ameriflux.products import (
    Collection,
    Policy,
    Product,
    info,
    validate,
)

Level = Literal["required", "recommended"]

CITE_EACH_SITE = "Cite each site's DOI in the reference list (not in supplementary material)."
DOE_SERVICE = (
    "Acknowledge: 'Funding for the AmeriFlux data service was provided by the U.S. Department "
    "of Energy Office of Science.'"
)
DOE_PORTAL = (
    "Acknowledge: 'Funding for the AmeriFlux data portal was provided by the U.S. Department of "
    "Energy Office of Science.'"
)


@dataclass(frozen=True)
class Obligation:
    text: str
    level: Level
    policy: Policy
    collection: Collection


@dataclass
class EffectivePolicy:
    collection: Collection
    code: Policy
    reason: str
    obligations: list[Obligation]
    #: Sites that cannot be used with this product (e.g. Legacy sites for FLUXNET).
    ineligible: dict[str, str] = field(default_factory=dict)


def obligations(
    collection: Collection, code: Policy, product: Product | None = None
) -> list[Obligation]:
    """What a policy asks of a user, for one collection."""

    def ob(text: str, level: Level = "required") -> Obligation:
        return Obligation(text, level, code, collection)

    if collection == "ameriflux":
        fluxnet_ack = (
            [
                ob(
                    "Add the FLUXNET acknowledgment: 'FLUXNET data products were produced and "
                    "harmonized by eddy covariance regional networks and data processing "
                    "centers, including AmeriFlux, ChinaFlux, European Fluxes Database, ICOS, "
                    "JapanFlux, KoFlux, OzFlux, SAEON, and TERN. These products also include a "
                    "modified version of ERA5 hourly data provided by the Copernicus Climate "
                    "Change Service.'"
                )
            ]
            if product == "FLUXNET"
            else []
        )
        if code == "LEGACY":
            return [
                ob(
                    "Contact the site PIs when you start in-depth analysis; they may offer "
                    "co-authorship."
                ),
                ob(CITE_EACH_SITE),
                ob(
                    "Acknowledge each site's funding (from its DOI record's sponsors or the BADM "
                    "GRP_ACKNOWLEDGEMENT)."
                ),
                ob(DOE_PORTAL),
                *fluxnet_ack,
                ob("Inform the data providers before publication."),
                ob("Use the AmeriFlux logo or link (ameriflux.lbl.gov) in presentations."),
            ]
        return [
            ob(CITE_EACH_SITE),
            ob(DOE_SERVICE),
            *fluxnet_ack,
            ob(
                "If the paper has a Data Availability section: 'The AmeriFlux [DATA PRODUCT] were "
                "accessed from [SOURCE] on XX Month YYYY.'",
                "recommended",
            ),
            ob("Inform the data providers about forthcoming publications.", "recommended"),
        ]
    name = info("FLUXNET2015" if collection == "fluxnet2015" else "FLUXNET-CH4").label
    base = [ob(f"Cite each site's DOI ({name}).")]
    if collection == "fluxnet2015":
        base.append(
            ob(
                "Cite Pastorello et al. (2020), Sci Data 7, 225, "
                "https://doi.org/10.1038/s41597-020-0534-3."
            )
        )
    if code == "TIER2":
        base.extend(
            [
                ob("Use the data for scientific and educational purposes only."),
                ob(
                    "Give the data providers at least three weeks to contribute after the first "
                    "draft is complete; they may become co-authors."
                ),
            ]
        )
        if collection == "fluxnet2015":
            base.append(
                ob(
                    "Tier-Two-only sites (RU-Sam, RU-SkP, RU-Tks, RU-Vrk, SE-St1, ZA-Kru) are not "
                    "part of Pastorello et al. (2020); cite their own references."
                )
            )
    return base


def effective_policy(
    product: Product, sites: Sequence[SiteRecord], requested: Policy | None = None
) -> EffectivePolicy:
    """The policy one selection of sites must follow for ``product``."""
    entry = info(product)
    if requested is not None:
        validate(product, requested)
    collection = entry.collection
    ineligible: dict[str, str] = {}
    if collection == "ameriflux":
        legacy = [s.site_id for s in sites if s.policy == "LEGACY"]
        if product == "FLUXNET":
            for site_id in legacy:
                ineligible[site_id] = (
                    "shares its data under the AmeriFlux Legacy policy; the FLUXNET product "
                    "exists only for CC-BY-4.0 sites"
                )
            code: Policy = "CCBY4.0"
            reason = "the AmeriFlux FLUXNET product is CC-BY-4.0 only"
        elif requested == "LEGACY":
            code, reason = "LEGACY", "LEGACY was requested"
        elif legacy:
            code = "LEGACY"
            reason = (
                f"{', '.join(legacy)} use{'s' if len(legacy) == 1 else ''} the Legacy policy; "
                "mixing CC-BY-4.0 and Legacy data means Legacy applies to all"
            )
        else:
            code, reason = "CCBY4.0", "every selected site shares its data under CC-BY-4.0"
    else:
        tiers = [s.fluxnet2015 if collection == "fluxnet2015" else s.fluxnet_ch4 for s in sites]
        tier2_only = [s.site_id for s, t in zip(sites, tiers, strict=True) if t and t.tier2_only]
        for site, tier in zip(sites, tiers, strict=True):
            if tier is None:
                ineligible[site.site_id] = f"is not part of {entry.label}"
        if requested == "TIER2":
            code, reason = "TIER2", "TIER2 was requested"
        elif tier2_only:
            code = "TIER2"
            reason = (
                f"{', '.join(tier2_only)} {'is' if len(tier2_only) == 1 else 'are'} Tier Two "
                "only; mixing tiers means Tier Two applies to all"
            )
        else:
            code, reason = "CCBY4.0", "every selected site is Tier One (CC-BY-4.0)"
    return EffectivePolicy(
        collection=collection,
        code=code,
        reason=reason,
        obligations=obligations(collection, code, product),
        ineligible=ineligible,
    )


def union(policies: Iterable[EffectivePolicy]) -> list[Obligation]:
    """Every obligation of several collections, de-duplicated, in order."""
    seen: set[tuple[str, str]] = set()
    out: list[Obligation] = []
    for policy in policies:
        for item in policy.obligations:
            key = (item.collection, item.text)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


__all__ = [
    "EffectivePolicy",
    "Obligation",
    "effective_policy",
    "obligations",
    "union",
]
