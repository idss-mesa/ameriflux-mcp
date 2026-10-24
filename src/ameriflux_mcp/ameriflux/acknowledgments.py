"""Verbatim acknowledgment and reference text from the data-policy pages (RESEARCH.md E25, E59, E61).

Quoted exactly as AmeriFlux and FLUXNET publish them, with the page and the date each
was last checked; the nightly live test checks that every string still appears on its
page. :mod:`ameriflux_mcp.ameriflux.policy` builds obligations from these, and
``ameriflux://reference/acknowledgments`` serves them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AMERIFLUX_POLICY_URL = "https://ameriflux.lbl.gov/data/data-policy/"
FLUXNET_POLICY_URL = "https://fluxnet.org/data/data-policy/"
CHECKED = "2026-10-24"


@dataclass(frozen=True)
class Text:
    key: str
    text: str
    applies_to: str
    source: str


DOE_DATA_SERVICE = Text(
    "doe_data_service",
    "Funding for the AmeriFlux data service was provided by the U.S. Department of Energy "
    "Office of Science.",
    "AmeriFlux data under the CC-BY-4.0 license",
    AMERIFLUX_POLICY_URL,
)
DOE_DATA_PORTAL = Text(
    "doe_data_portal",
    "Funding for the AmeriFlux data portal was provided by the U.S. Department of Energy "
    "Office of Science.",
    "AmeriFlux data under the Legacy Data Policy",
    AMERIFLUX_POLICY_URL,
)
FLUXNET_NETWORKS = Text(
    "fluxnet_networks",
    "FLUXNET data products were produced and harmonized by eddy covariance regional networks "
    "and data processing centers, including AmeriFlux, ChinaFlux, European Fluxes Database, "
    "ICOS, JapanFlux, KoFlux, OzFlux, SAEON, and TERN. These products also include a modified "
    "version of ERA5 hourly data provided by the Copernicus Climate Change Service.",
    "the AmeriFlux FLUXNET product, added to the DOE acknowledgment",
    AMERIFLUX_POLICY_URL,
)
DATA_AVAILABILITY = Text(
    "data_availability",
    "The AmeriFlux [DATA PRODUCT] were accessed from [SOURCE] on XX Month YYYY",
    "a paper's Data Availability section, in addition to the citations",
    AMERIFLUX_POLICY_URL,
)
#: The [SOURCE] choices the AmeriFlux policy lists.
DATA_SOURCES: tuple[str, ...] = (
    "the AmeriFlux data portal",
    "AmeriFlux APIs",
    "FLUXNET User Interface for the Shuttle",
    "the FLUXNET Shuttle code",
)
#: [DATA PRODUCT] per product argument.
DATA_PRODUCT_NAMES: dict[str, str] = {
    "BASE-BADM": "BASE data",
    "BIF": "BADM",
    "FLUXNET": "FLUXNET data",
}

CHU_2023 = Text(
    "chu_2023",
    "Chu, H., Christianson, D.S., Cheah, YW. et al. AmeriFlux BASE data pipeline to support "
    "network growth and data sharing. Sci Data 10, 614 (2023). "
    "https://doi.org/10.1038/s41597-023-02531-2",
    "data processing of AmeriFlux BASE",
    AMERIFLUX_POLICY_URL,
)
PASTORELLO_2020 = Text(
    "pastorello_2020",
    "Pastorello, G., Trotta, C., Canfora, E. et al. The FLUXNET2015 dataset and the ONEFlux "
    "processing pipeline for eddy covariance data. Sci Data 7, 225 (2020). "
    "https://doi.org/10.1038/s41597-020-0534-3",
    "data processing of AmeriFlux FLUXNET; the data-collection paper of FLUXNET2015",
    AMERIFLUX_POLICY_URL,
)

ALL: tuple[Text, ...] = (
    DOE_DATA_SERVICE,
    DOE_DATA_PORTAL,
    FLUXNET_NETWORKS,
    DATA_AVAILABILITY,
    CHU_2023,
    PASTORELLO_2020,
)


def processing_references(product: str) -> list[Text]:
    """The processing papers the policy recommends for a product."""
    if product in ("BASE-BADM", "BIF"):
        return [CHU_2023]
    if product in ("FLUXNET", "FLUXNET2015"):
        return [PASTORELLO_2020]
    return []


def as_resource() -> dict[str, Any]:
    """``ameriflux://reference/acknowledgments``."""
    return {
        "checked": CHECKED,
        "texts": [
            {"key": t.key, "text": t.text, "appliesTo": t.applies_to, "source": t.source}
            for t in ALL
        ],
        "dataSources": list(DATA_SOURCES),
        "fluxnet2015": {
            "source": FLUXNET_POLICY_URL,
            "ccby": [
                "Cite the data-collection paper (Pastorello et al. 2020).",
                "List each site used by its FLUXNET ID and/or per-site DOI in the paper.",
                "Recommended: inform data providers of forthcoming publications.",
            ],
            "tier2": [
                "Contact the data providers when you begin research that could lead to a "
                "publication.",
                "Give the data providers at least three weeks after the first draft is "
                "completed to contribute; substantive contributions result in co-authorship.",
                "Cite Pastorello et al. 2020 (Tier-Two-only sites are not part of it) and list "
                "each site by its FLUXNET ID and/or DOI in a table.",
                "Scientific and educational use only.",
            ],
            "mixing": "In case of a synthesis using both CC-BY-4.0 and Tier Two data, all data "
            "should be treated as Tier Two.",
        },
    }


__all__ = [
    "ALL",
    "AMERIFLUX_POLICY_URL",
    "CHU_2023",
    "DATA_AVAILABILITY",
    "DATA_PRODUCT_NAMES",
    "DATA_SOURCES",
    "DOE_DATA_PORTAL",
    "DOE_DATA_SERVICE",
    "FLUXNET_NETWORKS",
    "FLUXNET_POLICY_URL",
    "PASTORELLO_2020",
    "Text",
    "as_resource",
    "processing_references",
]
