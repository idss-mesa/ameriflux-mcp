"""Live smoke tests against the real AmeriFlux API (opt-in: ``AMERIFLUX_MCP_LIVE=1``).

GET only, paced by the client's rate limiter. Counts are asserted within ±10% of the
2026-10-22 values (RESEARCH.md E13–E18, E43), so normal network growth does not fail
the nightly job but a broken endpoint or a changed contract does.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from ameriflux_mcp.ameriflux.catalog import Catalog
from ameriflux_mcp.ameriflux.client import AmeriFluxClient
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
