"""The site catalog: AmeriFlux, FLUXNET2015 and FLUXNET-CH4 sites in one index.

Built from three cached responses (DESIGN.md D7, D20, D22):

* ``v2/site_info_display/AmeriFlux``: 856 AmeriFlux sites with policy, DOIs,
  published years, networks, team and BASE variables (E13);
* ``v1/site_display/FLUXNET/FLUXNET2015``: 212 sites with CC-BY and Tier 2 year
  ranges (E18, E49);
* ``v1/site_display/FLUXNET/FLUXNET-CH4``: 81 sites (E43).

A site in both an AmeriFlux and a FLUXNET list is one record whose ``collections``
names both. Sites only in a FLUXNET list (DE-Tha, GL-ZaF, ...) get the sparser
FLUXNET fields. Team emails stay in memory only; the disk cache never holds them
(D19), so records rebuilt from disk have none.

:class:`SiteIndex` answers case-insensitive ID lookups, NEON codes and fuzzy name
matches (scoring ported from neon-mcp: every query word must be accounted for
before a match can reach the acceptance threshold).
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from ameriflux_mcp.ameriflux.crosswalk import neon_code
from ameriflux_mcp.ameriflux.endpoints import FLUXNET_SITES, SITE_INFO
from ameriflux_mcp.models.upstream import (
    FluxnetSiteRow,
    SiteInfoRow,
    parse_rows,
    to_float,
)

if TYPE_CHECKING:
    from ameriflux_mcp.ameriflux.client import AmeriFluxClient
    from ameriflux_mcp.context import UpstreamStats

CollectionName = Literal["ameriflux", "fluxnet2015", "fluxnet_ch4"]
_WORD_RE = re.compile(r"[a-z0-9]+")
#: url_fluxnet holds this bare placeholder for sites without a FLUXNET page.
_FLUXNET_PLACEHOLDER = "https://fluxnet.org"


@dataclass(frozen=True)
class TeamMember:
    name: str
    role: str | None
    institution: str | None
    #: Present only in memory, and returned only under D19's two-flag rule.
    email: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class TierYears:
    """FLUXNET2015 / FLUXNET-CH4 year ranges by policy ("1991-2012")."""

    ccby: str | None
    tier2: str | None

    @property
    def tier2_only(self) -> bool:
        return self.ccby is None and self.tier2 is not None


@dataclass(frozen=True)
class SiteRecord:
    site_id: str
    name: str
    collections: frozenset[CollectionName]
    country: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    igbp: str | None = None
    koeppen: str | None = None
    mat_c: float | None = None
    map_mm: float | None = None
    status: str | None = None
    #: AmeriFlux data policy: CCBY4.0 or LEGACY (None for FLUXNET-only sites).
    policy: str | None = None
    networks: tuple[str, ...] = ()
    base_years: tuple[int, ...] = ()
    fluxnet_years: tuple[int, ...] = ()
    dois: Mapping[str, str] = field(default_factory=dict)
    base_variables: tuple[str, ...] = ()
    disturbance: tuple[str, ...] = ()
    gas_species: tuple[str, ...] = ()
    team: tuple[TeamMember, ...] = ()
    description: str | None = None
    url: str | None = None
    url_ameriflux: str | None = None
    url_fluxnet: str | None = None
    tower_start: str | None = None
    tower_end: str | None = None
    fluxnet2015: TierYears | None = None
    fluxnet_ch4: TierYears | None = None
    neon_code: str | None = None

    @property
    def search_text(self) -> str:
        return " ".join(
            filter(None, (self.site_id, self.name, self.state, self.country, self.neon_code))
        )


@dataclass(frozen=True)
class Candidate:
    code: str
    label: str
    score: float


def words(text: str | None) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _fuzzy_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _word_hit(word: str, vocab: set[str]) -> bool:
    return word in vocab or any(_fuzzy_ratio(word, v) >= 0.85 for v in vocab)


def name_score(query: str, name: str, extra_words: Iterable[str] = ()) -> float:
    """0..1 similarity driven by word coverage (ported from neon-mcp's catalog)."""
    q_words = words(query)
    n_words = words(name)
    if not q_words or not n_words:
        return 0.0
    q, n = " ".join(q_words), " ".join(n_words)
    if q == n:
        return 1.0
    if f" {q} " in f" {n} ":
        return 0.95 if n.startswith(q) else 0.9
    name_vocab = set(n_words)
    extra_vocab = {w for text in extra_words for w in words(text)}
    name_hits = sum(1 for w in q_words if _word_hit(w, name_vocab))
    extra_hits = sum(
        1 for w in q_words if not _word_hit(w, name_vocab) and _word_hit(w, extra_vocab)
    )
    if name_hits == len(q_words):
        return 0.85
    if name_hits + extra_hits == len(q_words) and name_hits > 0:
        return 0.78
    coverage = (name_hits + 0.5 * extra_hits) / len(q_words)
    return round(0.3 + 0.3 * coverage, 3)


def _years(values: Iterable[Any]) -> tuple[int, ...]:
    return tuple(sorted({int(v) for v in values if isinstance(v, int) and not isinstance(v, bool)}))


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _from_site_info(row: SiteInfoRow) -> SiteRecord:
    loc, clim = row.grp_location, row.grp_clim_avg
    networks = tuple(n for n in row.grp_network if isinstance(n, str))
    url_fluxnet = row.url_fluxnet
    if url_fluxnet and url_fluxnet.rstrip("/") == _FLUXNET_PLACEHOLDER:
        url_fluxnet = None
    return SiteRecord(
        site_id=row.site_id,
        name=row.site_name,
        collections=frozenset({"ameriflux"}),
        country=row.country,
        state=row.state,
        latitude=to_float(loc.get("location_lat")),
        longitude=to_float(loc.get("location_long")),
        elevation_m=to_float(loc.get("location_elev")),
        igbp=_str(row.grp_igbp.get("igbp")),
        koeppen=_str(clim.get("climate_koeppen")),
        mat_c=to_float(clim.get("mat")),
        map_mm=to_float(clim.get("map")),
        status=row.status,
        policy=row.publish_ameriflux_policy,
        networks=networks,
        base_years=_years(row.grp_publish_base),
        fluxnet_years=_years(row.grp_publish_fluxnet),
        dois={k: v for k, v in row.doi.items() if isinstance(v, str) and v},
        base_variables=tuple(row.base_variables),
        disturbance=tuple(row.dom_dist_mgmt),
        gas_species=tuple(dict.fromkeys(g for g in row.flux_measurements_variables if g)),
        team=tuple(
            TeamMember(
                name=m.team_member_name,
                role=m.team_member_role,
                institution=m.team_member_institution,
                email=m.team_member_email,
            )
            for m in row.grp_team_member
            if m.team_member_name
        ),
        description=row.site_desc,
        url=row.url,
        url_ameriflux=row.url_ameriflux,
        url_fluxnet=url_fluxnet,
        tower_start=_str(row.tower_dates.get("tower_start")),
        tower_end=_str(row.tower_dates.get("tower_end")),
        neon_code=neon_code(row.site_name, networks),
    )


def _tiers(row: FluxnetSiteRow) -> TierYears:
    return TierYears(ccby=row.CCBY4_0, tier2=row.Tier2)


def _from_fluxnet(row: FluxnetSiteRow, collection: CollectionName) -> SiteRecord:
    loc, clim = row.GRP_LOCATION, row.GRP_CLIM_AVG
    tiers = _tiers(row)
    return SiteRecord(
        site_id=row.SITE_ID,
        name=row.SITE_NAME,
        collections=frozenset({collection}),
        country=row.COUNTRY,
        state=row.STATE,
        latitude=to_float(loc.get("LOCATION_LAT")),
        longitude=to_float(loc.get("LOCATION_LONG")),
        elevation_m=to_float(loc.get("LOCATION_ELEV")),
        igbp=row.IGBP,
        mat_c=to_float(clim.get("MAT")),
        map_mm=to_float(clim.get("MAP")),
        url_fluxnet=row.URL_AMERIFLUX,
        tower_start=row.TOWER_BEGAN,
        tower_end=row.TOWER_END,
        fluxnet2015=tiers if collection == "fluxnet2015" else None,
        fluxnet_ch4=tiers if collection == "fluxnet_ch4" else None,
    )


def _merge(record: SiteRecord, row: FluxnetSiteRow, collection: CollectionName) -> SiteRecord:
    tiers = _tiers(row)
    return replace(
        record,
        collections=record.collections | {collection},
        fluxnet2015=tiers if collection == "fluxnet2015" else record.fluxnet2015,
        fluxnet_ch4=tiers if collection == "fluxnet_ch4" else record.fluxnet_ch4,
        url_fluxnet=record.url_fluxnet or row.URL_AMERIFLUX,
    )


class SiteIndex:
    """Every known site, with case-insensitive, NEON-code and fuzzy lookups."""

    def __init__(self, records: Iterable[SiteRecord], *, built_at: float) -> None:
        self.records: dict[str, SiteRecord] = {r.site_id: r for r in sorted(records, key=_key)}
        self._fold = {sid.casefold(): sid for sid in self.records}
        self._neon = {r.neon_code: r.site_id for r in self.records.values() if r.neon_code}
        self.built_at = built_at

    def __len__(self) -> int:
        return len(self.records)

    def lookup(self, site_id: str) -> SiteRecord | None:
        canonical = self._fold.get(site_id.strip().casefold())
        return self.records[canonical] if canonical else None

    def by_neon_code(self, code: str) -> SiteRecord | None:
        site_id = self._neon.get(code.strip().upper())
        return self.records[site_id] if site_id else None

    def in_collection(self, collection: CollectionName) -> list[SiteRecord]:
        return [r for r in self.records.values() if collection in r.collections]

    def similar_ids(self, text: str, n: int = 3) -> list[str]:
        folded = {sid.casefold(): sid for sid in self.records}
        return [folded[m] for m in difflib.get_close_matches(text.casefold(), folded, n=n)]

    def fuzzy_candidates(self, text: str, n: int = 8) -> list[Candidate]:
        cands = [
            Candidate(
                r.site_id,
                r.name,
                round(name_score(text, r.name, (r.state or "", r.country or "")), 3),
            )
            for r in self.records.values()
        ]
        cands = [c for c in cands if c.score > 0.3]
        cands.sort(key=lambda c: (-c.score, c.code))
        return cands[:n]


def _key(record: SiteRecord) -> str:
    return record.site_id


def build_index(
    site_info: Sequence[Any],
    fluxnet2015: Sequence[Any],
    fluxnet_ch4: Sequence[Any],
    *,
    built_at: float,
) -> SiteIndex:
    records: dict[str, SiteRecord] = {}
    for info_row in parse_rows(SiteInfoRow, site_info, endpoint=SITE_INFO.name):
        records[info_row.site_id] = _from_site_info(info_row)
    lists: tuple[tuple[Sequence[Any], CollectionName], ...] = (
        (fluxnet2015, "fluxnet2015"),
        (fluxnet_ch4, "fluxnet_ch4"),
    )
    for rows, collection in lists:
        for row in parse_rows(FluxnetSiteRow, rows, endpoint=FLUXNET_SITES.name):
            existing = records.get(row.SITE_ID)
            records[row.SITE_ID] = (
                _merge(existing, row, collection)
                if existing is not None
                else _from_fluxnet(row, collection)
            )
    return SiteIndex(records.values(), built_at=built_at)


class Catalog:
    """Process-wide catalog service on top of the client's cache."""

    def __init__(
        self, client: AmeriFluxClient, *, wall_clock: Callable[[], float] = time.time
    ) -> None:
        self.client = client
        self._wall = wall_clock
        self._index: SiteIndex | None = None
        self._sources: tuple[int, int, int] | None = None
        self._lock = asyncio.Lock()

    def peek(self) -> SiteIndex | None:
        """The last built index without any request (``None`` when cold)."""
        return self._index

    async def index(self, stats: UpstreamStats) -> SiteIndex:
        site_info, f15, ch4 = await asyncio.gather(
            self.client.fetch(SITE_INFO, stats=stats),
            self.client.fetch(FLUXNET_SITES, stats=stats, product="FLUXNET2015"),
            self.client.fetch(FLUXNET_SITES, stats=stats, product="FLUXNET-CH4"),
        )
        sources = (id(site_info), id(f15), id(ch4))
        async with self._lock:
            if self._index is None or self._sources != sources:
                self._index = build_index(site_info, f15, ch4, built_at=self._wall())
                self._sources = sources
            return self._index


__all__ = [
    "Candidate",
    "Catalog",
    "SiteIndex",
    "SiteRecord",
    "TeamMember",
    "TierYears",
    "build_index",
    "name_score",
    "words",
]
