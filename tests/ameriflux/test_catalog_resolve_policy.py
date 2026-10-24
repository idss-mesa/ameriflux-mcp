"""Catalog, resolution and policy against the recorded fixtures (fixture site set only)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ameriflux_mcp.ameriflux.catalog import Catalog, SiteIndex, name_score
from ameriflux_mcp.ameriflux.client import AmeriFluxClient
from ameriflux_mcp.ameriflux.crosswalk import neon_code, neon_crosswalk
from ameriflux_mcp.ameriflux.policy import effective_policy, obligations, union
from ameriflux_mcp.ameriflux.resolve import resolve_site, resolve_sites
from ameriflux_mcp.config import CacheConfig, UpstreamConfig
from ameriflux_mcp.context import UpstreamStats
from ameriflux_mcp.errors import ToolError
from tests.fixture_router import FIXTURE_SITES, FixtureRouter


@pytest.fixture
async def catalog(router: FixtureRouter, tmp_path: Path) -> AsyncIterator[Catalog]:
    client = AmeriFluxClient(
        UpstreamConfig(), CacheConfig(), disk_dir=tmp_path, http_transport=router.transport
    )
    yield Catalog(client)
    await client.aclose()


@pytest.fixture
async def index(catalog: Catalog) -> SiteIndex:
    return await catalog.index(UpstreamStats())


# ---------------------------------------------------------------------- catalog


async def test_index_merges_the_three_lists(index: SiteIndex) -> None:
    assert set(index.records) == set(FIXTURE_SITES)
    ha1 = index.records["US-Ha1"]
    assert ha1.collections == {"ameriflux", "fluxnet2015"}
    assert ha1.policy == "CCBY4.0" and ha1.igbp == "DBF" and ha1.state == "MA"
    assert ha1.latitude == pytest.approx(42.5378) and ha1.koeppen == "Dfb"
    assert ha1.dois == {"AmeriFlux": "10.17190/AMF/1246059", "FLUXNET": "10.17190/AMF/1871137"}
    assert ha1.base_years[0] == 1991 and ha1.fluxnet_years[0] == 1991
    assert ha1.fluxnet2015 is not None and ha1.fluxnet2015.ccby == "1991-2012"
    assert "LTER" in ha1.networks and ha1.team and ha1.team[0].role == "PI"
    assert ha1.url_fluxnet == "https://fluxnet.org/sites/siteinfo/US-Ha1"


async def test_fluxnet_only_and_tier2_only_sites(index: SiteIndex) -> None:
    tha = index.records["DE-Tha"]
    assert tha.collections == {"fluxnet2015"} and tha.policy is None and tha.country
    sam = index.records["RU-Sam"]
    assert sam.fluxnet2015 is not None and sam.fluxnet2015.tier2_only
    myb = index.records["US-Myb"]
    assert {"ameriflux", "fluxnet_ch4"} <= myb.collections
    assert myb.fluxnet_ch4 is not None and myb.fluxnet_ch4.ccby
    assert index.records["CA-Let"].policy == "LEGACY"
    assert len(index.in_collection("fluxnet_ch4")) == 2


async def test_placeholder_fluxnet_url_is_dropped(index: SiteIndex) -> None:
    assert index.records["US-xSR"].url_fluxnet is None


async def test_catalog_builds_once_per_source_generation(catalog: Catalog) -> None:
    assert catalog.peek() is None
    first = await catalog.index(UpstreamStats())
    stats = UpstreamStats()
    second = await catalog.index(stats)
    assert second is first and stats.requests == 0 and stats.cache_hits == 3


async def test_emails_stay_in_memory_only(catalog: Catalog, tmp_path: Path) -> None:
    index = await catalog.index(UpstreamStats())
    assert any(m.email for m in index.records["US-Ha1"].team)
    assert "@" not in "".join(p.read_text() for p in tmp_path.rglob("*.json"))


def test_neon_codes() -> None:
    assert neon_code("NEON Santa Rita Experimental Range (SRER)", ["AmeriFlux", "NEON"]) == "SRER"
    assert neon_code("Harvard Forest EMS Tower (HFR1)", ["AmeriFlux", "LTER"]) is None
    assert neon_code("NEON site without code", ["NEON"]) is None


async def test_neon_crosswalk(index: SiteIndex) -> None:
    assert neon_crosswalk(index) == [
        {
            "neonSiteCode": "GUAN",
            "siteId": "PR-xGU",
            "siteName": "NEON Guanica Forest (GUAN)",
        },
        {
            "neonSiteCode": "SRER",
            "siteId": "US-xSR",
            "siteName": "NEON Santa Rita Experimental Range (SRER)",
        },
    ]


def test_name_score() -> None:
    assert name_score("Harvard Forest EMS Tower (HFR1)", "Harvard Forest EMS Tower (HFR1)") == 1.0
    assert name_score("harvard forest", "Harvard Forest EMS Tower (HFR1)") == 0.95
    assert name_score("Blue Ridge", "Blue River") < 0.75


# ---------------------------------------------------------------------- resolve


@pytest.mark.parametrize(
    ("text", "site", "resolved"),
    [
        ("US-Ha1", "US-Ha1", False),
        ("us-ha1", "US-Ha1", True),
        ("US-XSR", "US-xSR", True),
        ("SRER", "US-xSR", True),
        ("guan", "PR-xGU", True),
        ("DK-ZaF", "GL-ZaF", True),
        ("Santa Rita", "US-xSR", True),
        ("Mayberry Wetland", "US-Myb", True),
    ],
)
async def test_resolve_site(index: SiteIndex, text: str, site: str, resolved: bool) -> None:
    result = resolve_site(text, index)
    assert result.site_id == site
    assert (result.resolved is not None) is resolved
    if resolved:
        assert result.resolved is not None and result.resolved.code == site


async def test_rename_and_neon_notes(index: SiteIndex) -> None:
    assert "renamed GL-ZaF" in resolve_site("DK-ZaF", index).notes[0]
    assert "NEON site code" in resolve_site("SRER", index).notes[0]


async def test_ambiguous_name(index: SiteIndex) -> None:
    with pytest.raises(ToolError) as exc:
        resolve_site("Harvard Forest", index)
    assert exc.value.code == "ambiguous_input"
    candidates = [c["siteId"] for c in exc.value.details["candidates"]]
    assert {"US-Ha1", "US-Ha2", "US-Ha3"} <= set(candidates)


async def test_unknown_inputs(index: SiteIndex) -> None:
    with pytest.raises(ToolError) as unknown_id:
        resolve_site("US-Ha9", index)
    assert unknown_id.value.code == "not_found"
    assert "US-Ha1" in unknown_id.value.details["didYouMean"]
    with pytest.raises(ToolError) as nothing:
        resolve_site("Zzyzx Qwerty", index)
    assert nothing.value.code == "not_found"
    for bad, code in (("", "invalid_argument"), ("AA-Flx", "invalid_argument")):
        with pytest.raises(ToolError) as exc:
            resolve_site(bad, index)
        assert exc.value.code == code


async def test_resolve_sites_dedupes(index: SiteIndex) -> None:
    out = resolve_sites(["US-Ha1", "us-ha1", "SRER", "US-xSR"], index)
    assert [r.site_id for r in out] == ["US-Ha1", "US-xSR"]


# ---------------------------------------------------------------------- policy


async def test_ccby_selection(index: SiteIndex) -> None:
    policy = effective_policy("BASE-BADM", [index.records["US-Ha1"], index.records["US-xSR"]])
    assert policy.code == "CCBY4.0" and policy.collection == "ameriflux"
    texts = [o.text for o in policy.obligations]
    assert any("data service" in t for t in texts)
    assert {o.level for o in policy.obligations} == {"required", "recommended"}


async def test_legacy_escalates(index: SiteIndex) -> None:
    policy = effective_policy("BASE-BADM", [index.records["US-Ha1"], index.records["CA-Let"]])
    assert policy.code == "LEGACY" and "CA-Let" in policy.reason
    texts = " ".join(o.text for o in policy.obligations)
    assert "data portal" in texts and "Contact the site PIs" in texts and "logo" in texts
    assert effective_policy("BASE-BADM", [index.records["US-Ha1"]], "LEGACY").code == "LEGACY"


async def test_fluxnet_product_excludes_legacy_sites(index: SiteIndex) -> None:
    policy = effective_policy("FLUXNET", [index.records["US-Ha1"], index.records["CA-Let"]])
    assert policy.code == "CCBY4.0" and set(policy.ineligible) == {"CA-Let"}
    assert any("ERA5" in o.text for o in policy.obligations)
    with pytest.raises(ToolError) as exc:
        effective_policy("FLUXNET", [index.records["US-Ha1"]], "LEGACY")
    assert exc.value.details["reason"] == "fluxnet_requires_ccby"


async def test_tier_two_escalates(index: SiteIndex) -> None:
    mixed = effective_policy("FLUXNET2015", [index.records["US-Ha1"], index.records["RU-Sam"]])
    assert mixed.code == "TIER2" and "RU-Sam" in mixed.reason
    texts = " ".join(o.text for o in mixed.obligations)
    assert "three weeks" in texts and "Pastorello" in texts and "not part of" in texts
    tier1 = effective_policy("FLUXNET2015", [index.records["US-Ha1"]])
    assert tier1.code == "CCBY4.0"
    outsider = effective_policy("FLUXNET2015", [index.records["US-Ha2"]])
    assert set(outsider.ineligible) == {"US-Ha2"}


async def test_union_across_collections(index: SiteIndex) -> None:
    sites = [index.records["US-Myb"]]
    both = union([effective_policy("BASE-BADM", sites), effective_policy("FLUXNET-CH4", sites)])
    assert {o.collection for o in both} == {"ameriflux", "fluxnet_ch4"}
    assert len(both) == len({(o.collection, o.text) for o in both})


def test_obligation_tables() -> None:
    assert obligations("fluxnet_ch4", "CCBY4.0")[0].text.startswith("Cite each site's DOI")
    assert not any("Pastorello" in o.text for o in obligations("fluxnet_ch4", "CCBY4.0"))
