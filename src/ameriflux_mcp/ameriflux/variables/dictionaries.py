"""The FP Standard and FLUXNET variable dictionaries (DESIGN.md D35).

* **FP Standard** (BASE): live from ``v1/fp_var?limits=True`` (cached 24 h), falling back
  to the bundled snapshot ``fp-variables.json`` when the API cannot be reached, with a
  note giving the snapshot's date. Each variable carries units, type, the plausible
  range AmeriFlux uses for QA/QC (Min, Max) and its height direction.
* **FLUXNET** (FLUXNET2015 FULLSET/SUBSET and the AmeriFlux FLUXNET product, ONEFlux
  v1.3): the committed ``fluxnet-variables.json``, built by
  ``scripts/build_variable_dictionaries.py``. Units change with resolution (NEE is
  µmolCO2 m-2 s-1 at HH, gC m-2 d-1 at DD–MM, gC m-2 y-1 at YY), so every entry has
  units and notes per resolution. Names with placeholders (``NEE_VUT_XX``,
  ``TS_F_MDS_#``) stand for their concrete forms; see
  :func:`~ameriflux_mcp.ameriflux.variables.grammar.fluxnet_template`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ameriflux_mcp.ameriflux.endpoints import FP_VAR
from ameriflux_mcp.errors import AmeriFluxApiError
from ameriflux_mcp.models.upstream import FpVarRow, parse_rows

if TYPE_CHECKING:
    from ameriflux_mcp.context import ToolContext

STATIC_DIR = Path(__file__).resolve().parents[2] / "resources_static"
RESOLUTIONS: tuple[str, ...] = ("HH", "DD", "WW", "MM", "YY")
Resolution = Literal["HH", "DD", "WW", "MM", "YY"]
RESOLUTION_LABELS: dict[str, str] = {
    "HH": "half-hourly or hourly",
    "DD": "daily",
    "WW": "weekly",
    "MM": "monthly",
    "YY": "yearly",
}
HEIGHT_DIRECTIONS: dict[str, str] = {
    "pos": "above the surface (heights in m)",
    "neg": "below the surface (depths, reported as negative heights)",
}
#: Sign conventions for the CO2 flux products (RESEARCH.md section 7).
SIGN_CONVENTIONS: dict[str, str] = {
    "NEE": "Negative NEE is uptake by the ecosystem; NEE = RECO - GPP.",
    "FC": "Negative FC is uptake by the ecosystem (flux from the atmosphere to the surface).",
    "GPP": "GPP is positive (uptake); NEE = RECO - GPP.",
    "RECO": "RECO is positive (release); NEE = RECO - GPP.",
}


@dataclass(frozen=True)
class FpVariable:
    name: str
    type: str | None
    units: str | None
    description: str | None
    min: float | None
    max: float | None
    height_direction: str | None
    model_type: str | None


@dataclass(frozen=True)
class FluxnetVariable:
    name: str
    section: str | None
    description: str | None
    units: Mapping[str, str | None]
    notes: Mapping[str, str]
    fullset: bool
    subset: bool
    #: Resolutions ONEFlux v1.3 (the AmeriFlux FLUXNET product) defines this name at.
    oneflux: tuple[str, ...]
    members: str | None

    def available_at(self, resolution: str) -> bool:
        return self.notes.get(resolution) != "not available" and (
            self.units.get(resolution) is not None or resolution in self.oneflux
        )


@dataclass(frozen=True)
class FpList:
    variables: tuple[FpVariable, ...]
    live: bool
    fetched: str | None
    notes: tuple[str, ...] = ()

    def by_name(self) -> dict[str, FpVariable]:
        return {v.name: v for v in self.variables}


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((STATIC_DIR / name).read_text(encoding="utf-8"))
    return data


@lru_cache(maxsize=1)
def fluxnet_dictionary() -> dict[str, FluxnetVariable]:
    out: dict[str, FluxnetVariable] = {}
    for row in _load("fluxnet-variables.json")["variables"]:
        out[row["name"]] = FluxnetVariable(
            name=row["name"],
            section=row.get("section"),
            description=row.get("description"),
            units=dict(row["units"]),
            notes=dict(row.get("notes") or {}),
            fullset=bool(row.get("fullset")),
            subset=bool(row.get("subset")),
            oneflux=tuple(row.get("oneflux") or ()),
            members=row.get("members"),
        )
    return out


@lru_cache(maxsize=1)
def fluxnet_sources() -> dict[str, Any]:
    sources: dict[str, Any] = _load("fluxnet-variables.json")["sources"]
    return sources


def _fp_from_snapshot_row(row: Mapping[str, Any]) -> FpVariable:
    return FpVariable(
        name=str(row["name"]),
        type=row.get("type"),
        units=row.get("units"),
        description=row.get("description"),
        min=row.get("min"),
        max=row.get("max"),
        height_direction=row.get("heightDirection"),
        model_type=row.get("modelType"),
    )


@lru_cache(maxsize=1)
def fp_snapshot() -> FpList:
    data = _load("fp-variables.json")
    return FpList(
        variables=tuple(_fp_from_snapshot_row(r) for r in data["variables"]),
        live=False,
        fetched=data.get("fetched"),
    )


async def fp_variables(ctx: ToolContext) -> FpList:
    """The live FP Standard list; the bundled snapshot (with a note) if the API fails."""
    if ctx.client is None:  # pragma: no cover - every server builds a client
        return fp_snapshot()
    try:
        rows = await ctx.client.fetch(FP_VAR, stats=ctx.stats)
        parsed = parse_rows(FpVarRow, rows, endpoint="v1/fp_var")
    except AmeriFluxApiError as exc:
        snapshot = fp_snapshot()
        return FpList(
            variables=snapshot.variables,
            live=False,
            fetched=snapshot.fetched,
            notes=(
                f"The live FP Standard list was unavailable ({exc.service}: {exc.status or exc.kind}); "
                f"using the bundled snapshot of {snapshot.fetched}.",
            ),
        )
    return FpList(
        variables=tuple(
            FpVariable(
                name=r.Name,
                type=r.Type,
                units=r.Units,
                description=r.Description,
                min=r.Min,
                max=r.Max,
                height_direction=r.HeightDirection,
                model_type=r.ModelType,
            )
            for r in parsed
        ),
        live=True,
        fetched=None,
    )


__all__ = [
    "HEIGHT_DIRECTIONS",
    "RESOLUTIONS",
    "RESOLUTION_LABELS",
    "SIGN_CONVENTIONS",
    "FluxnetVariable",
    "FpList",
    "FpVariable",
    "Resolution",
    "fluxnet_dictionary",
    "fluxnet_sources",
    "fp_snapshot",
    "fp_variables",
]
