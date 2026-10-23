"""The AmeriFlux API endpoints ameriflux-mcp reads: version, envelope, required keys.

The API has no published contract and v1 and v2 are asymmetric (RESEARCH.md E12,
E14), so each endpoint records its own version and envelope (DESIGN.md D4):

* ``bare``: a JSON array (v1);
* ``values``: ``{"values": [...]}`` (v2);
* ``object``: a JSON object.

:func:`unwrap` checks the envelope and the required keys (D8). A missing key or a
changed envelope raises :class:`~ameriflux_mcp.errors.AmeriFluxApiError` with
``kind="drift"``, which tools report as ``upstream_error`` with ``details.drift``.
The DOI endpoint answers 200 with ``{}`` or ``{"status": "No valid DOI for …"}``
when there is no DOI (E19, E20); :func:`unwrap` returns ``None`` for those.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ameriflux_mcp.ameriflux.cache import CacheFamily
from ameriflux_mcp.errors import AmeriFluxApiError

Envelope = Literal["bare", "values", "object"]


@dataclass(frozen=True)
class Endpoint:
    name: str
    version: Literal["v1", "v2"]
    template: str
    envelope: Envelope
    #: Keys every row (or the object) must carry.
    required: frozenset[str]
    family: CacheFamily
    query: Mapping[str, str] = field(default_factory=dict)

    def path(self, **params: str) -> str:
        return f"{self.version}/{self.template.format(**params)}"

    def family_for(self, **params: str) -> CacheFamily:
        """Availability of the frozen FLUXNET-network releases caches for 30 days."""
        if self.name == "data_availability" and params.get("network") == "FLUXNET":
            return "fluxnet2015"
        return self.family


SITE_INFO = Endpoint(
    "site_info",
    "v2",
    "site_info_display/AmeriFlux",
    "values",
    frozenset(
        {
            "site_id",
            "site_name",
            "country",
            "grp_location",
            "grp_igbp",
            "grp_network",
            "status",
            "publish_ameriflux_policy",
            "doi",
            "grp_publish_base",
            "grp_publish_fluxnet",
        }
    ),
    "catalog",
)
FLUXNET_SITES = Endpoint(
    "fluxnet_sites",
    "v1",
    "site_display/FLUXNET/{product}",
    "bare",
    frozenset({"SITE_ID", "SITE_NAME", "COUNTRY", "GRP_LOCATION", "IGBP", "Tier2"}),
    "fluxnet2015",
)
SITE_AVAILABILITY = Endpoint(
    "site_availability",
    "v1",
    "site_availability",
    "object",
    frozenset({"AmeriFlux", "FLUXNET"}),
    "availability",
)
DATA_AVAILABILITY = Endpoint(
    "data_availability",
    "v1",
    "data_availability/{network}/{product}/{policy}",
    "bare",
    frozenset({"SITE_ID", "publish_years"}),
    "availability",
)
FP_VAR = Endpoint(
    "fp_var",
    "v1",
    "fp_var",
    "bare",
    frozenset({"Name", "Type", "Units", "Description", "Min", "Max"}),
    "variables",
    {"limits": "True"},
)
DOI = Endpoint(
    "doi",
    "v1",
    "DOI/{site}/{product}",
    "object",
    frozenset({"DOI_INFO", "DOI_CONTRIBUTOR", "REFERENCES"}),
    "citations",
)

ENDPOINTS: dict[str, Endpoint] = {
    e.name: e for e in (SITE_INFO, FLUXNET_SITES, SITE_AVAILABILITY, DATA_AVAILABILITY, FP_VAR, DOI)
}


def _drift(endpoint: Endpoint, label: str, detail: str, missing: list[str]) -> AmeriFluxApiError:
    return AmeriFluxApiError(200, detail, label, kind="drift", missing=missing)


def unwrap(endpoint: Endpoint, payload: Any, label: str) -> Any:
    """Check the envelope and required keys; return rows (list), an object, or ``None``."""
    if endpoint.envelope == "values":
        if not isinstance(payload, dict) or not isinstance(payload.get("values"), list):
            raise _drift(endpoint, label, "expected {'values': [...]}", ["values"])
        rows: Any = payload["values"]
    elif endpoint.envelope == "bare":
        if not isinstance(payload, list):
            raise _drift(endpoint, label, "expected a JSON array", [])
        rows = payload
    else:
        if not isinstance(payload, dict):
            raise _drift(endpoint, label, "expected a JSON object", [])
        if endpoint is DOI and (not payload or set(payload) == {"status"}):
            return None  # "no DOI for this site and product" (E19, E20)
        missing = sorted(endpoint.required - set(payload))
        if missing:
            raise _drift(endpoint, label, "required keys are missing", missing)
        return payload
    missing_counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise _drift(endpoint, label, "expected objects in the array", [])
        for key in endpoint.required - set(row):
            missing_counts[key] = missing_counts.get(key, 0) + 1
    if missing_counts:
        raise _drift(
            endpoint,
            label,
            f"required keys are missing in {max(missing_counts.values())} of {len(rows)} rows",
            sorted(missing_counts),
        )
    return rows


__all__ = [
    "DATA_AVAILABILITY",
    "DOI",
    "ENDPOINTS",
    "FLUXNET_SITES",
    "FP_VAR",
    "SITE_AVAILABILITY",
    "SITE_INFO",
    "Endpoint",
    "unwrap",
]
