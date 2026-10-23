"""Typed views of AmeriFlux API rows (DESIGN.md D8).

``extra="allow"``: new upstream keys are tolerated; the required keys are checked
per endpoint by :func:`ameriflux_mcp.ameriflux.endpoints.unwrap`. v1 sends every
value as a string ("42.5378"); these models coerce numbers and treat ``""`` as
missing. :func:`parse_rows` turns a row that does not validate into a drift error.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ameriflux_mcp.errors import AmeriFluxApiError

M = TypeVar("M", bound=BaseModel)


class _Upstream(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


def to_float(value: Any) -> float | None:
    """``"42.5378"`` -> 42.5378; ``""``, ``None`` and junk -> ``None``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        return float(text) if text else None
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return int(number) if number is not None and number == int(number) else None


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class TeamMemberRow(_Upstream):
    team_member_name: str | None = None
    team_member_role: str | None = None
    team_member_institution: str | None = None
    team_member_email: str | None = None


class SiteInfoRow(_Upstream):
    """One site of ``v2/site_info_display/AmeriFlux``."""

    site_id: str
    site_name: str
    country: str | None = None
    state: str | None = None
    site_desc: str | None = None
    status: str | None = None
    grp_location: dict[str, Any] = Field(default_factory=dict)
    grp_igbp: dict[str, Any] = Field(default_factory=dict)
    grp_clim_avg: dict[str, Any] = Field(default_factory=dict)
    grp_network: list[str] = Field(default_factory=list)
    grp_team_member: list[TeamMemberRow] = Field(default_factory=list)
    url: str | None = None
    url_ameriflux: str | None = None
    url_fluxnet: str | None = None
    dom_dist_mgmt: list[str] = Field(default_factory=list)
    flux_measurements_variables: list[str] = Field(default_factory=list)
    base_variables: list[str] = Field(default_factory=list)
    publish_ameriflux_policy: str | None = None
    doi: dict[str, str] = Field(default_factory=dict)
    grp_publish_base: list[int] = Field(default_factory=list)
    grp_publish_fluxnet: list[int] = Field(default_factory=list)
    tower_dates: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "country",
        "state",
        "site_desc",
        "status",
        "url",
        "url_ameriflux",
        "url_fluxnet",
        "publish_ameriflux_policy",
        mode="before",
    )
    @classmethod
    def _blank(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator(
        "grp_location",
        "grp_igbp",
        "grp_clim_avg",
        "doi",
        "tower_dates",
        mode="before",
    )
    @classmethod
    def _dict(cls, value: Any) -> Any:
        return value or {}

    @field_validator(
        "grp_network",
        "grp_team_member",
        "dom_dist_mgmt",
        "flux_measurements_variables",
        "base_variables",
        "grp_publish_base",
        "grp_publish_fluxnet",
        mode="before",
    )
    @classmethod
    def _list(cls, value: Any) -> Any:
        return value or []


class FluxnetSiteRow(_Upstream):
    """One site of ``v1/site_display/FLUXNET/{FLUXNET2015|FLUXNET-CH4}`` (sparse, E49)."""

    SITE_ID: str
    SITE_NAME: str
    COUNTRY: str | None = None
    STATE: str | None = None
    GRP_LOCATION: dict[str, Any] = Field(default_factory=dict)
    IGBP: str | None = None
    GRP_CLIM_AVG: dict[str, Any] = Field(default_factory=dict)
    TOWER_BEGAN: str | None = None
    TOWER_END: str | None = None
    #: Year range under CC-BY-4.0, e.g. "1991-2012"; absent for Tier-2-only sites.
    CCBY4_0: str | None = None
    Tier2: str | None = None
    URL_AMERIFLUX: str | None = None

    @field_validator(
        "COUNTRY", "STATE", "IGBP", "TOWER_BEGAN", "TOWER_END", "CCBY4_0", "Tier2", mode="before"
    )
    @classmethod
    def _blank(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("GRP_LOCATION", "GRP_CLIM_AVG", mode="before")
    @classmethod
    def _dict(cls, value: Any) -> Any:
        return value or {}


class AvailabilityRow(_Upstream):
    """One row of ``v1/data_availability/{network}/{product}/{policy}``."""

    SITE_ID: str
    URL: str | None = None
    publish_years: list[int] = Field(default_factory=list)

    @field_validator("publish_years", mode="before")
    @classmethod
    def _list(cls, value: Any) -> Any:
        return value or []


class FpVarRow(_Upstream):
    """One FP Standard variable of ``v1/fp_var?limits=True``."""

    Name: str
    Type: str | None = None
    Units: str | None = None
    Description: str | None = None
    Sequence: int | None = None
    ModelType: str | None = None
    HeightDirection: str | None = None
    Min: float | None = None
    Max: float | None = None

    @field_validator("Sequence", mode="before")
    @classmethod
    def _int(cls, value: Any) -> Any:
        return to_int(value)

    @field_validator("Min", "Max", mode="before")
    @classmethod
    def _float(cls, value: Any) -> Any:
        return to_float(value)


def parse_rows(model: type[M], rows: Iterable[Any], *, endpoint: str) -> list[M]:
    """Validate every row; a row that does not fit raises a drift error."""
    out: list[M] = []
    for row in rows:
        try:
            out.append(model.model_validate(row))
        except ValidationError as exc:
            fields = sorted(
                {str(err["loc"][0]) for err in exc.errors(include_input=False) if err["loc"]}
            )
            raise AmeriFluxApiError(
                200,
                f"a row does not match {model.__name__}",
                endpoint,
                kind="drift",
                missing=fields,
            ) from None
    return out


__all__ = [
    "AvailabilityRow",
    "FluxnetSiteRow",
    "FpVarRow",
    "SiteInfoRow",
    "TeamMemberRow",
    "parse_rows",
    "to_float",
    "to_int",
]
