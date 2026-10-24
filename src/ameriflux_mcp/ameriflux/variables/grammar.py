"""The variable-name grammar of AmeriFlux BASE and FLUXNET data (DESIGN.md D35).

**BASE names** (FP Standard; RESEARCH.md section 7, the AmeriFlux data-variables page):
a base name from the FP Standard list, then general qualifiers in this order: ``_PI``
(provided by the tower team), ``_QC`` (quality flag), ``_F`` (gap-filled), ``_IU``
(instrument units); then at most one position: ``_H_V_R`` (three indices: horizontal,
vertical, replicate), ``_H_V_A`` (replicates averaged) or ``_#`` (layer aggregate), the
last two optionally followed by ``_SD`` or ``_N``. ``FETCH_70``, ``FETCH_FILTER`` and
``<FLUX>_SSITC_TEST`` are base names in their own right. The classification follows
amerifluxr's ``amf_parse_basename`` (BSD-3, see NOTICE) but tokenizes the name instead
of matching regular expressions anywhere in it, so the base name is always the longest
FP Standard prefix and nothing inside it is mistaken for a qualifier.

**FLUXNET names** (ONEFlux, FLUXNET2015) extend a base name with processing tokens
(``_F_MDS``, ``_ERA``, ``_VUT``/``_CUT`` with ``_REF``/``_USTAR50``/percentiles,
``_NT``/``_DT``/``_SR``, ``_RANDUNC``, ``_CORR``, ``_DAY``/``_NIGHT``, ``_QC`` …).
They are explained token by token; whether a name exists is the FLUXNET dictionary's
call, looked up by :func:`fluxnet_template` (``NEE_VUT_05`` -> ``NEE_VUT_XX``,
``TS_F_MDS_2`` -> ``TS_F_MDS_#``).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

GENERAL: tuple[str, ...] = ("PI", "QC", "F", "IU")
GENERAL_MEANINGS: dict[str, str] = {
    "PI": "provided by the tower team: QA/QC-filtered or gap-filled by the PI, independently "
    "of network processing",
    "QC": "quality-control flag from AmeriFlux's standard, centralized QA/QC",
    "F": "gap-filled",
    "IU": "instrument units (counts, mV, absorbance) instead of standard units",
}
GENERAL_KINDS: dict[str, str] = {"PI": "pi", "QC": "qc", "F": "gapfill", "IU": "instrument_units"}
PERCENTILES: tuple[str, ...] = ("05", "16", "25", "50", "75", "84", "95")
STATISTICS: dict[str, str] = {
    "SD": "standard deviation across the aggregated sensors",
    "N": "number of sensors aggregated",
}
#: FLUXNET processing tokens (FULLSET/SUBSET pages, ONEFlux var_info; RESEARCH.md section 7).
FLUXNET_TOKENS: dict[str, tuple[str, str]] = {
    "ERA": (
        "gapfill",
        "downscaled from ERA reanalysis (ERA-Interim in FLUXNET2015, ERA5 in "
        "the AmeriFlux FLUXNET product)",
    ),
    "JSB": ("gapfill", "computed with the JSBACH algorithm from TA, SW_IN and VPD"),
    "VUT": ("ustar", "variable USTAR threshold, one per year"),
    "CUT": ("ustar", "constant USTAR threshold across years"),
    "REF": (
        "realization",
        "reference realization, chosen by model efficiency (MEF) among up to 40 versions",
    ),
    "USTAR50": ("realization", "realization from the 50th-percentile USTAR threshold"),
    "MEAN": ("realization", "mean of the USTAR-threshold realizations"),
    "SE": ("realization", "standard error of the USTAR-threshold realizations"),
    "XX": ("percentile", "percentile placeholder: XX = 05, 16, 25, 50, 75, 84, 95"),
    "RANDUNC": ("uncertainty", "random uncertainty"),
    "JOINTUNC": ("uncertainty", "joint uncertainty (random plus USTAR filtering)"),
    "METHOD": ("uncertainty", "method code"),
    "CORR": ("correction", "energy-balance corrected"),
    "DAY": ("daypart", "daytime average"),
    "NIGHT": ("daypart", "nighttime average"),
    "SD": ("statistic", "standard deviation"),
    "N": ("statistic", "number of data points used"),
    "QC": (
        "qc",
        "quality flag: categorical at HH, fraction of measured and good gap-filled "
        "data at DD and coarser",
    ),
    "POT": ("derived", "potential (top of atmosphere)"),
}
PARTITIONING: dict[str, str] = {
    "NT": "nighttime partitioning method",
    "DT": "daytime partitioning method",
    "SR": "sundown respiration partitioning method",
}

Grammar = Literal["base", "fluxnet", "unknown"]
PositionKind = Literal["sensor", "replicate_average", "layer_average"]


@dataclass(frozen=True)
class Token:
    """One qualifier or processing token, as written (``_PI``, ``_1_1_1``, ``_VUT``)."""

    text: str
    kind: str
    meaning: str


@dataclass(frozen=True)
class Position:
    kind: PositionKind
    h: int | None = None
    v: int | None = None
    r: int | None = None
    layer: int | None = None
    statistic: Literal["SD", "N"] | None = None

    @property
    def text(self) -> str:
        if self.kind == "sensor":
            core = f"_{self.h}_{self.v}_{self.r}"
        elif self.kind == "replicate_average":
            core = f"_{self.h}_{self.v}_A"
        else:
            core = f"_{self.layer}"
        return core + (f"_{self.statistic}" if self.statistic else "")

    @property
    def meaning(self) -> str:
        if self.kind == "sensor":
            text = (
                f"sensor at horizontal position {self.h}, vertical position {self.v} "
                f"(1 = highest or shallowest), replicate {self.r}"
            )
        elif self.kind == "replicate_average":
            text = (
                f"average of the replicate sensors at horizontal position {self.h}, vertical "
                f"position {self.v}"
            )
        else:
            text = f"aggregate of the horizontal positions in layer {self.layer} (1 = highest)"
        return text + (f"; {STATISTICS[self.statistic]}" if self.statistic else "")


@dataclass(frozen=True)
class ParsedName:
    name: str
    basename: str | None
    known_basename: bool
    grammar: Grammar
    general: tuple[str, ...] = ()
    position: Position | None = None
    tokens: tuple[Token, ...] = ()
    #: The FLUXNET dictionary key this name would have (``NEE_VUT_XX``, ``TS_F_MDS_#``).
    template: str | None = None
    unknown: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def is_gapfilled(self) -> bool:
        return "F" in self.general or any(t.kind == "gapfill" for t in self.tokens)

    @property
    def is_qc(self) -> bool:
        return "QC" in self.general or any(t.kind == "qc" for t in self.tokens)


@lru_cache(maxsize=1)
def snapshot_fp_names() -> frozenset[str]:
    """FP Standard base names from the bundled snapshot (``fp-variables.json``)."""
    path = Path(__file__).resolve().parents[2] / "resources_static" / "fp-variables.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["variables"]
    return frozenset(str(r["name"]) for r in rows)


def _split(name: str, fp_names: Collection[str]) -> tuple[str | None, list[str]]:
    """The longest FP Standard prefix (whole tokens) and the remaining tokens."""
    tokens = name.split("_")
    for cut in range(len(tokens), 0, -1):
        candidate = "_".join(tokens[:cut])
        if candidate in fp_names:
            return candidate, tokens[cut:]
    return None, tokens


def _parse_base(rest: Sequence[str]) -> tuple[tuple[str, ...], Position | None] | None:
    """BASE qualifiers after the base name, or ``None`` if ``rest`` breaks the grammar."""
    general: list[str] = []
    i = 0
    while i < len(rest) and rest[i] in GENERAL:
        if general and GENERAL.index(rest[i]) <= GENERAL.index(general[-1]):
            return None  # repeated or out of order
        general.append(rest[i])
        i += 1
    position: Position | None = None
    tail = rest[i:]
    if len(tail) >= 3 and tail[0].isdigit() and tail[1].isdigit() and tail[2].isdigit():
        position = Position("sensor", h=int(tail[0]), v=int(tail[1]), r=int(tail[2]))
        i += 3
    elif len(tail) >= 3 and tail[0].isdigit() and tail[1].isdigit() and tail[2] == "A":
        position = Position("replicate_average", h=int(tail[0]), v=int(tail[1]))
        i += 3
    elif tail and tail[0].isdigit():
        position = Position("layer_average", layer=int(tail[0]))
        i += 1
    if (
        position is not None
        and position.kind != "sensor"
        and i < len(rest)
        and rest[i] in STATISTICS
    ):
        position = Position(
            position.kind,
            h=position.h,
            v=position.v,
            layer=position.layer,
            statistic=rest[i],  # type: ignore[arg-type]
        )
        i += 1
    if i != len(rest):
        return None
    return tuple(general), position


def fluxnet_template(name: str) -> str:
    """The FLUXNET dictionary key for a concrete name: percentiles -> XX, layers -> #."""
    tokens = name.upper().split("_")
    out: list[str] = []
    for i, token in enumerate(tokens):
        prev = tokens[i - 1] if i else ""
        if token in PERCENTILES and prev in ("VUT", "CUT"):
            out.append("XX")
        elif token.isdigit() and prev == "MDS":
            out.append("#")
        else:
            out.append(token)
    return "_".join(out)


def _fluxnet_tokens(basename: str, rest: Sequence[str]) -> tuple[list[Token], list[str]]:
    tokens: list[Token] = []
    unknown: list[str] = []
    i = 0
    while i < len(rest):
        token = rest[i]
        prev = rest[i - 1] if i else basename.rsplit("_", 1)[-1]
        nxt = rest[i + 1] if i + 1 < len(rest) else None
        if token == "F" and nxt == "MDS":
            tokens.append(
                Token("_F_MDS", "gapfill", "gap-filled with marginal distribution sampling (MDS)")
            )
            i += 2
            if i < len(rest) and (rest[i].isdigit() or rest[i] == "#"):
                tokens.append(Token(f"_{rest[i]}", "layer", "soil layer index (1 = shallowest)"))
                i += 1
            continue
        if token == "F":
            tokens.append(
                Token(
                    "_F",
                    "gapfill",
                    "consolidated: measured where good quality, else MDS gap-filled, else "
                    "downscaled from ERA",
                )
            )
        elif token in PERCENTILES and prev in ("VUT", "CUT"):
            tokens.append(
                Token(
                    f"_{token}",
                    "percentile",
                    f"{token}th percentile of the USTAR-threshold realizations",
                )
            )
        elif token in ("25", "75") and prev == "CORR":
            tokens.append(
                Token(
                    f"_{token}",
                    "correction",
                    f"{token}th percentile of the energy-balance correction factor",
                )
            )
        elif token in PARTITIONING and basename in ("GPP", "RECO"):
            tokens.append(Token(f"_{token}", "partitioning", PARTITIONING[token]))
        elif token in FLUXNET_TOKENS:
            kind, meaning = FLUXNET_TOKENS[token]
            tokens.append(Token(f"_{token}", kind, meaning))
        elif token.isdigit():
            tokens.append(Token(f"_{token}", "layer", "layer or position index"))
        else:
            unknown.append(token)
        i += 1
    return tokens, unknown


def parse(name: str, fp_names: Collection[str] | None = None) -> ParsedName:
    """Decompose one variable name. ``fp_names`` defaults to the bundled FP snapshot."""
    names = snapshot_fp_names() if fp_names is None else fp_names
    text = name.strip().upper()
    basename, rest = _split(text, names)
    notes: list[str] = []
    if basename is not None:
        if basename.startswith("FETCH_") and basename != "FETCH_FILTER":
            notes.append("FETCH_* is a footprint distance in its own right, not a position.")
        if basename.endswith("_SSITC_TEST"):
            notes.append(
                "SSITC test flag (Foken et al. 2004): 0 = best, 1 = medium, 2 = poorest quality."
            )
        if basename == "FETCH_FILTER":
            notes.append("FETCH_FILTER: 0 = discard (outside the footprint), 1 = keep.")
        base = _parse_base(rest)
        if base is not None:
            general, position = base
            tokens = [Token(f"_{g}", GENERAL_KINDS[g], GENERAL_MEANINGS[g]) for g in general]
            if position is not None:
                tokens.append(Token(position.text, position.kind, position.meaning))
            return ParsedName(
                name=text,
                basename=basename,
                known_basename=True,
                grammar="base",
                general=general,
                position=position,
                tokens=tuple(tokens),
                template=fluxnet_template(text),
                notes=tuple(notes),
            )
    fluxnet_base = basename or rest[0]
    fluxnet_rest = rest if basename else rest[1:]
    tokens, unknown = _fluxnet_tokens(fluxnet_base, fluxnet_rest)
    grammar: Grammar = "fluxnet" if basename is not None and not unknown else "unknown"
    if basename is None:
        notes.append(f"{fluxnet_base} is not an FP Standard base name.")
    return ParsedName(
        name=text,
        basename=basename or fluxnet_base,
        known_basename=basename is not None,
        grammar=grammar,
        tokens=tuple(tokens),
        template=fluxnet_template(text),
        unknown=tuple(unknown),
        notes=tuple(notes),
    )


def compose(basename: str, general: Sequence[str] = (), position: Position | None = None) -> str:
    """Inverse of :func:`parse` for BASE names: ``compose('TA', ['F'], Position(...))``."""
    ordered = [g for g in GENERAL if g in general]
    if len(ordered) != len(general):
        raise ValueError(f"general qualifiers must be a subset of {GENERAL} without repeats")
    return basename + "".join(f"_{g}" for g in ordered) + (position.text if position else "")


__all__ = [
    "FLUXNET_TOKENS",
    "GENERAL",
    "GENERAL_KINDS",
    "GENERAL_MEANINGS",
    "PARTITIONING",
    "PERCENTILES",
    "ParsedName",
    "Position",
    "Token",
    "compose",
    "fluxnet_template",
    "parse",
    "snapshot_fp_names",
]
