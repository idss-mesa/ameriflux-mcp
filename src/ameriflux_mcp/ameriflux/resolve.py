"""Tolerant site resolution (DESIGN.md D20; thresholds from neon-mcp).

Accepted, in order:

1. an exact site ID, in any case (``us-ha1`` -> ``US-Ha1``);
2. a FLUXNET2015 rename (``DK-ZaF`` -> ``GL-ZaF``), echoed in ``resolved`` with a note;
3. a NEON site code (``SRER`` -> ``US-xSR``);
4. a site name, fuzzily: accepted when it is an exact name, or when its score is at
   least 0.75 **and** at least 1.15 times the runner-up. Otherwise the call fails with
   ``ambiguous_input`` (up to eight candidates) or ``not_found`` (with ``didYouMean``).

Resolution never elicits: ranked candidates serve agents better than a form.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ameriflux_mcp.ameriflux.catalog import Candidate, SiteIndex, SiteRecord
from ameriflux_mcp.ameriflux.products import BULK_SITES
from ameriflux_mcp.ameriflux.siteid import is_site_id, rename_note, renamed
from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.models.common import Resolved

ACCEPT_SCORE = 0.75
ACCEPT_MARGIN = 1.15
NOT_FOUND_BELOW = 0.45
MAX_CANDIDATES = 8


@dataclass
class SiteResolution:
    record: SiteRecord
    resolved: Resolved | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def site_id(self) -> str:
        return self.record.site_id


def _decide(candidates: Sequence[Candidate], *, field_name: str, value: str) -> Candidate:
    if not candidates or candidates[0].score < NOT_FOUND_BELOW:
        raise ToolError(
            "not_found",
            f"No AmeriFlux or FLUXNET site matches {value!r}.",
            details={
                "field": field_name,
                "input": value,
                "didYouMean": [{"siteId": c.code, "name": c.label} for c in candidates[:3]],
            },
            hint="Search with amf_search_sites, or pass a site ID such as US-Ha1.",
        )
    top = candidates[0]
    runner = candidates[1].score if len(candidates) > 1 else 0.0
    exact = top.score >= 1.0 and runner < 1.0
    if exact or (
        top.score >= ACCEPT_SCORE and (runner == 0.0 or top.score >= ACCEPT_MARGIN * runner)
    ):
        return top
    raise ToolError(
        "ambiguous_input",
        f"{value!r} matches several sites; call again with one of the candidate site IDs.",
        details={
            "field": field_name,
            "input": value,
            "candidates": [
                {"siteId": c.code, "name": c.label, "score": c.score}
                for c in candidates[:MAX_CANDIDATES]
            ],
        },
    )


def resolve_site(value: str, index: SiteIndex, *, field_name: str = "site") -> SiteResolution:
    """Resolve one site argument against the catalog."""
    text = value.strip()
    if not text:
        raise ToolError(
            "invalid_argument", f"{field_name} is empty.", details={"field": field_name}
        )
    if text in BULK_SITES:
        raise ToolError(
            "invalid_argument",
            f"{text} is a bulk BADM selector, not a site; it is valid only for BIF downloads.",
            details={"field": field_name, "input": text, "reason": "bulk_site"},
        )
    record = index.lookup(text)
    if record is not None:
        resolved = (
            None
            if record.site_id == text
            else Resolved(field=field_name, input=text, code=record.site_id, confidence=1.0)
        )
        return SiteResolution(record, resolved)
    new_id = renamed(text)
    if new_id is not None:
        record = index.lookup(new_id)
        if record is not None:
            return SiteResolution(
                record,
                Resolved(field=field_name, input=text, code=record.site_id, confidence=1.0),
                [rename_note(text, record.site_id)],
            )
    if is_site_id(text):
        raise ToolError(
            "not_found",
            f"Site {text!r} is not in the AmeriFlux, FLUXNET2015 or FLUXNET-CH4 catalogs.",
            details={"field": field_name, "input": text, "didYouMean": index.similar_ids(text)},
            hint="Search with amf_search_sites.",
        )
    if len(text) == 4 and text.isalpha():
        record = index.by_neon_code(text)
        if record is not None:
            return SiteResolution(
                record,
                Resolved(field=field_name, input=text, code=record.site_id, confidence=1.0),
                [f"{text.upper()} is the NEON site code of {record.site_id} ({record.name})."],
            )
    top = _decide(index.fuzzy_candidates(text, MAX_CANDIDATES), field_name=field_name, value=text)
    return SiteResolution(
        index.records[top.code],
        Resolved(field=field_name, input=text, code=top.code, confidence=round(top.score, 2)),
    )


def resolve_sites(
    values: Sequence[str], index: SiteIndex, *, field_name: str = "sites"
) -> list[SiteResolution]:
    """Resolve each element, de-duplicating while preserving order."""
    out: list[SiteResolution] = []
    seen: set[str] = set()
    for value in values:
        resolution = resolve_site(value, index, field_name=field_name)
        if resolution.site_id not in seen:
            seen.add(resolution.site_id)
            out.append(resolution)
    return out


__all__ = [
    "ACCEPT_MARGIN",
    "ACCEPT_SCORE",
    "MAX_CANDIDATES",
    "NOT_FOUND_BELOW",
    "SiteResolution",
    "resolve_site",
    "resolve_sites",
]
