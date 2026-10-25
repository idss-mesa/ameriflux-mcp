"""Products, policies and the network × product × policy matrix (DESIGN.md D6, D11).

The AmeriFlux API answers an invalid product or policy on the AmeriFlux network
with 200 and empty rows, so every combination is validated here before any
request (RESEARCH.md E15, E42). User input is normalized first: ``CC-BY-4.0``,
``Legacy``, ``Tier2``, ``base``, ``FLUXNET-1F`` and similar spellings are
accepted.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ameriflux_mcp.errors import ToolError

Network = Literal["AmeriFlux", "FLUXNET"]
Product = Literal["BASE-BADM", "BIF", "FLUXNET", "FLUXNET2015", "FLUXNET-CH4"]
Policy = Literal["CCBY4.0", "LEGACY", "TIER2"]
Collection = Literal["ameriflux", "fluxnet2015", "fluxnet_ch4"]

PRODUCTS: tuple[Product, ...] = ("BASE-BADM", "BIF", "FLUXNET", "FLUXNET2015", "FLUXNET-CH4")
POLICIES: tuple[Policy, ...] = ("CCBY4.0", "LEGACY", "TIER2")
#: Bulk BADM site IDs: every site, or every site with flux data (RESEARCH.md E44).
BULK_SITES = ("AA-Net", "AA-Flx")


@dataclass(frozen=True)
class ProductInfo:
    product: Product
    network: Network
    policies: tuple[Policy, ...]
    collection: Collection
    #: Product segment of ``v1/DOI/{site}/{segment}`` (D9).
    doi_segment: str
    label: str


MATRIX: dict[Product, ProductInfo] = {
    "BASE-BADM": ProductInfo(
        "BASE-BADM",
        "AmeriFlux",
        ("CCBY4.0", "LEGACY"),
        "ameriflux",
        "AmeriFlux",
        "AmeriFlux BASE (half-hourly/hourly flux and met data with BADM)",
    ),
    "BIF": ProductInfo(
        "BIF",
        "AmeriFlux",
        ("CCBY4.0", "LEGACY"),
        "ameriflux",
        "AmeriFlux",  # BADM is cited with the BASE DOI (D9)
        "AmeriFlux BADM site metadata (BIF)",
    ),
    "FLUXNET": ProductInfo(
        "FLUXNET",
        "AmeriFlux",
        ("CCBY4.0",),
        "ameriflux",
        "FLUXNET",
        "AmeriFlux FLUXNET (FLUXNET-1F, ONEFlux-processed)",
    ),
    "FLUXNET2015": ProductInfo(
        "FLUXNET2015",
        "FLUXNET",
        ("CCBY4.0", "TIER2"),
        "fluxnet2015",
        "FLUXNET2015",
        "FLUXNET2015 (FULLSET and SUBSET, frozen 2020 release)",
    ),
    "FLUXNET-CH4": ProductInfo(
        "FLUXNET-CH4",
        "FLUXNET",
        ("CCBY4.0", "TIER2"),
        "fluxnet_ch4",
        "FLUXNET-CH4",
        "FLUXNET-CH4 Community Product V1.0",
    ),
}

_PRODUCT_ALIASES: dict[str, Product] = {
    "base": "BASE-BADM",
    "basebadm": "BASE-BADM",
    "ameriflux": "BASE-BADM",
    "amerifluxbase": "BASE-BADM",
    "bif": "BIF",
    "badm": "BIF",
    "fluxnet": "FLUXNET",
    "fluxnet1f": "FLUXNET",
    "amerifluxfluxnet": "FLUXNET",
    "oneflux": "FLUXNET",
    "fluxnet2015": "FLUXNET2015",
    "fluxnetch4": "FLUXNET-CH4",
    "ch4": "FLUXNET-CH4",
}
_POLICY_ALIASES: dict[str, Policy] = {
    "ccby40": "CCBY4.0",
    "ccby4": "CCBY4.0",
    "ccby": "CCBY4.0",
    "tier1": "CCBY4.0",
    "tierone": "CCBY4.0",
    "legacy": "LEGACY",
    "amerifluxlegacy": "LEGACY",
    "tier2": "TIER2",
    "tiertwo": "TIER2",
}
_SQUASH = re.compile(r"[^a-z0-9]+")


def _squash(text: str) -> str:
    return _SQUASH.sub("", text.lower())


def normalize_product(text: str, *, field: str = "product") -> Product:
    """``base`` / ``BASE-BADM`` / ``FLUXNET-1F`` / ``fluxnet 2015`` -> a :data:`Product`."""
    product = _PRODUCT_ALIASES.get(_squash(text))
    if product is None:
        raise ToolError(
            "invalid_argument",
            f"Unknown product {text!r}.",
            details={"field": field, "input": text, "valid": list(PRODUCTS)},
            hint="Use BASE-BADM, BIF, FLUXNET, FLUXNET2015 or FLUXNET-CH4.",
        )
    return product


def normalize_policy(text: str, *, field: str = "policy") -> Policy:
    """``CC-BY-4.0`` / ``ccby4`` / ``Tier 1`` -> CCBY4.0; ``Legacy`` -> LEGACY; ``Tier2`` -> TIER2."""
    policy = _POLICY_ALIASES.get(_squash(text))
    if policy is None:
        raise ToolError(
            "invalid_argument",
            f"Unknown data policy {text!r}.",
            details={"field": field, "input": text, "valid": list(POLICIES)},
            hint="Use CCBY4.0, LEGACY (AmeriFlux) or TIER2 (FLUXNET2015, FLUXNET-CH4).",
        )
    return policy


def info(product: Product) -> ProductInfo:
    return MATRIX[product]


def validate(product: Product, policy: Policy) -> ProductInfo:
    """Fail with ``invalid_argument`` (``invalid_combination``) before any request."""
    entry = MATRIX[product]
    if policy not in entry.policies:
        reason = (
            "fluxnet_requires_ccby"
            if product == "FLUXNET" and policy == "LEGACY"
            else "invalid_combination"
        )
        message = (
            "The AmeriFlux FLUXNET product exists only for sites shared under CC-BY-4.0 "
            "(ONEFlux processes CC-BY data only)."
            if reason == "fluxnet_requires_ccby"
            else f"{product} has no {policy} data; valid policies: {', '.join(entry.policies)}."
        )
        raise ToolError(
            "invalid_argument",
            message,
            details={
                "reason": reason,
                "product": product,
                "policy": policy,
                "validPolicies": list(entry.policies),
            },
        )
    return entry


def availability_path(product: Product, policy: Policy) -> str | None:
    """``v1/data_availability/{network}/{product}/{policy}``, or ``None`` for BIF (D7)."""
    entry = validate(product, policy)
    if product == "BIF":
        return None  # its data_availability rows are always empty; use site_availability
    return f"v1/data_availability/{entry.network}/{product}/{policy}"


@dataclass(frozen=True)
class DownloadRequest:
    """What ``data_download`` receives for a tool request (D11; used from build step 7)."""

    data_product: Literal["BASE-BADM", "FLUXNET"]
    site_ids: tuple[str, ...]
    data_variant: Literal["FULLSET"] | None


def download_request(product: Product, sites: Sequence[str]) -> DownloadRequest:
    """Map a tool product to the request body: BIF goes as BASE-BADM with AA-Flx/AA-Net."""
    if product in ("FLUXNET2015", "FLUXNET-CH4"):
        raise ToolError(
            "feature_unavailable",
            f"{product} files are downloaded through fluxnet.org's login-protected form, which "
            "ameriflux-mcp does not automate.",
            details={"product": product, "guide": "ameriflux://guide/fluxnet2015-access"},
            hint="Download the zips yourself from fluxnet.org and read them with the local file "
            "tools (ameriflux://guide/fluxnet2015-access).",
        )
    ids = tuple(sites)
    if product == "BIF":
        bulk = [s for s in ids if s in BULK_SITES]
        if not bulk or len(bulk) != len(ids):
            raise ToolError(
                "invalid_argument",
                "Bulk BADM (BIF) is requested for AA-Flx (sites with flux data) or AA-Net (all "
                "sites); a single site's BADM comes inside its BASE-BADM download.",
                details={"reason": "bif_needs_bulk_site", "sites": list(ids)},
                hint="Use sites=['AA-Flx'] or ['AA-Net'], or product='BASE-BADM' for one site.",
            )
        return DownloadRequest("BASE-BADM", ids, None)
    if any(s in BULK_SITES for s in ids):
        raise ToolError(
            "invalid_argument",
            "AA-Flx and AA-Net are only valid with product='BIF'.",
            details={"reason": "bulk_site_needs_bif", "sites": list(ids)},
        )
    if product == "FLUXNET":
        return DownloadRequest("FLUXNET", ids, "FULLSET")  # D30
    return DownloadRequest("BASE-BADM", ids, None)


__all__ = [
    "BULK_SITES",
    "MATRIX",
    "POLICIES",
    "PRODUCTS",
    "Collection",
    "DownloadRequest",
    "Network",
    "Policy",
    "Product",
    "ProductInfo",
    "availability_path",
    "download_request",
    "info",
    "normalize_policy",
    "normalize_product",
    "validate",
]
