"""Live smoke tests against the real AmeriFlux API (opt-in: ``AMERIFLUX_MCP_LIVE=1``).

GET only, paced by the client's rate limiter. Counts are asserted within ±10% of the
2026-10-22 values (RESEARCH.md E13–E18, E43), so normal network growth does not fail
the nightly job but a broken endpoint or a changed contract does.
"""

from __future__ import annotations

import asyncio
import html
import os
import re
from collections.abc import AsyncIterator

import httpx
import pytest

from ameriflux_mcp.ameriflux import acknowledgments as ack
from ameriflux_mcp.ameriflux.catalog import Catalog
from ameriflux_mcp.ameriflux.citation import parse_datacite
from ameriflux_mcp.ameriflux.client import AmeriFluxClient, user_agent
from ameriflux_mcp.ameriflux.crosswalk import neon_crosswalk
from ameriflux_mcp.ameriflux.endpoints import (
    DATA_AVAILABILITY,
    DOI,
    FLUXNET_SITES,
    FP_VAR,
    SITE_AVAILABILITY,
    SITE_INFO,
)
from ameriflux_mcp.ameriflux.resolve import resolve_site
from ameriflux_mcp.ameriflux.variables import coverage, heights
from ameriflux_mcp.ameriflux.variables.dictionaries import fluxnet_sources
from ameriflux_mcp.config import CacheConfig, UpstreamConfig
from ameriflux_mcp.context import UpstreamStats
from ameriflux_mcp.errors import AmeriFluxApiError

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("AMERIFLUX_MCP_LIVE") != "1", reason="set AMERIFLUX_MCP_LIVE=1"
    ),
]


def about(actual: int, expected: int) -> bool:
    return abs(actual - expected) <= 0.1 * expected


def non_empty(rows: list[dict[str, object]]) -> set[str]:
    return {str(r["SITE_ID"]) for r in rows if r["publish_years"]}


@pytest.fixture
async def client() -> AsyncIterator[AmeriFluxClient]:
    c = AmeriFluxClient(UpstreamConfig(user_agent_suffix="live-tests"), CacheConfig())
    yield c
    await c.aclose()


async def test_live_catalog_and_crosswalk(client: AmeriFluxClient) -> None:
    rows = await client.fetch(SITE_INFO, stats=UpstreamStats())
    assert about(len(rows), 856)
    index = await Catalog(client).index(UpstreamStats())
    assert about(len(index.in_collection("fluxnet2015")), 212)
    assert about(len(index.in_collection("fluxnet_ch4")), 81)
    walk = neon_crosswalk(index)
    assert about(len(walk), 47)
    assert resolve_site("SRER", index).site_id == "US-xSR"
    assert index.records["US-Ha1"].dois["AmeriFlux"] == "10.17190/AMF/1246059"


async def test_live_availability_semantics(client: AmeriFluxClient) -> None:
    async def avail(network: str, product: str, policy: str) -> set[str]:
        rows = await client.fetch(
            DATA_AVAILABILITY,
            stats=UpstreamStats(),
            network=network,
            product=product,
            policy=policy,
        )
        return non_empty(rows)

    ccby = await avail("AmeriFlux", "BASE-BADM", "CCBY4.0")
    legacy = await avail("AmeriFlux", "BASE-BADM", "LEGACY")
    assert about(len(ccby), 533) and about(len(legacy), 610) and ccby <= legacy
    assert about(len(await avail("AmeriFlux", "FLUXNET", "CCBY4.0")), 407)
    assert await avail("AmeriFlux", "FLUXNET", "LEGACY") == set()
    f15_ccby = await avail("FLUXNET", "FLUXNET2015", "CCBY4.0")
    f15_tier2 = await avail("FLUXNET", "FLUXNET2015", "TIER2")
    assert about(len(f15_tier2), 212) and f15_ccby <= f15_tier2
    assert {"RU-Sam", "ZA-Kru"} <= f15_tier2 - f15_ccby
    assert about(len(await avail("FLUXNET", "FLUXNET-CH4", "CCBY4.0")), 79)
    tree = await client.fetch(SITE_AVAILABILITY, stats=UpstreamStats())
    assert about(len(tree["AmeriFlux"]["BIF"]["LEGACY"]), 843)


async def test_live_validation_quirks(client: AmeriFluxClient) -> None:
    with pytest.raises(AmeriFluxApiError) as exc:
        await client.get_json(
            "v1/data_availability/FLUXNET/FLUXNET2015/Tier2", stats=UpstreamStats()
        )
    assert exc.value.status == 422 and "TIER2, CCBY4.0" in exc.value.detail
    unvalidated = await client.get_json(
        "v1/data_availability/AmeriFlux/BASE-BADM/Tier2", stats=UpstreamStats()
    )
    assert unvalidated and not non_empty(unvalidated)


async def test_live_variables_and_dois(client: AmeriFluxClient) -> None:
    rows = await client.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    assert 140 <= len(rows) <= 160
    ha1 = await client.fetch(DOI, stats=UpstreamStats(), site="US-Ha1", product="AmeriFlux")
    assert "Ver." in ha1["DOI_INFO"]["DOI_CITATION"]
    for product in ("BASE", "BIF"):
        assert (
            await client.fetch(DOI, stats=UpstreamStats(), site="US-Ha1", product=product) is None
        )
    f15 = await client.fetch(FLUXNET_SITES, stats=UpstreamStats(), product="FLUXNET2015")
    assert about(len(f15), 212)


async def test_live_variable_sources(client: AmeriFluxClient) -> None:
    """The step-5 sources: heights page and CSV, coverage snapshot, webdoc ETags, DataCite."""
    stats = UpstreamStats()
    link = await client.fetch_url(
        heights.HEIGHTS_PAGE, family="heights", parse=heights.parse_page, stats=stats
    )
    rows = await client.fetch_url(
        link["url"], family="heights", parse=heights.parse_csv, stats=stats
    )
    assert about(len(rows), 587)  # sites in BASE_MeasurementHeight_20260908.csv
    assert any(r[0] == "TA_1_1_1" for r in rows["US-Ha1"])
    snapshot = await client.fetch_url(
        coverage.COVERAGE_URL,
        family="coverage",
        parse=coverage.parse_csv,
        stats=stats,
        max_bytes=coverage.MAX_BYTES,
    )
    assert snapshot["created"] and "US-Ha1" in snapshot["sites"]
    for key, meta in fluxnet_sources().items():
        if key in ("fullset", "subset"):
            head = await client.request("HEAD", meta["url"], stats=stats)
            assert head.headers.get("etag") == meta["etag"], f"{key} dictionary changed upstream"
    meta = await client.fetch_url(
        "https://api.datacite.org/dois/10.17190/AMF/1246059",
        family="citations",
        parse=parse_datacite,
        stats=stats,
    )
    assert meta["creators"] and meta["year"]


async def test_live_policy_texts_unchanged() -> None:
    """Every verbatim acknowledgment still appears on its policy page (test-only GETs)."""
    await asyncio.sleep(15)  # ameriflux.lbl.gov asks for a 15 s crawl delay (E37)
    headers = {"User-Agent": user_agent("live-tests")}
    async with httpx.AsyncClient(headers=headers, timeout=60, follow_redirects=False) as http:
        amf = await http.get(ack.AMERIFLUX_POLICY_URL)
        fluxnet = await http.get(ack.FLUXNET_POLICY_URL)
    amf_text, fluxnet_text = _page_text(amf.text), _page_text(fluxnet.text)
    for text in ack.ALL:
        assert text.text in amf_text, text.key
    assert ack.as_resource()["fluxnet2015"]["mixing"] in fluxnet_text


def _page_text(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return re.sub(r"\s+", " ", text).replace("“", "").replace("”", "")
