"""amf_get_availability against the recorded fixtures (15 fixture sites)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ameriflux_mcp.server import AmeriFluxServer
from tests.fixture_router import FixtureRouter
from tests.helpers import call_err, call_ok


async def avail(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_get_availability", args)


def rows_by(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["siteId"], r["product"]): r for r in payload["rows"]}


async def test_default_products_follow_collections(server: AmeriFluxServer) -> None:
    payload = await avail(server, sites=["US-Ha1", "RU-Sam", "US-Myb"])
    rows = rows_by(payload)
    ha1 = rows[("US-Ha1", "BASE-BADM")]
    assert ha1["policy"] == "CCBY4.0" and ha1["first"] == 1991 and ha1["count"] >= 35
    assert ("US-Ha1", "FLUXNET") in rows and ("US-Ha1", "FLUXNET2015") in rows
    assert rows[("RU-Sam", "FLUXNET2015")]["policy"] == "TIER2"
    assert rows[("US-Myb", "FLUXNET-CH4")]["policy"] == "CCBY4.0"
    assert payload["summary"]["sitesWithData"] == 3


async def test_legacy_site_rows_and_fluxnet_gap(server: AmeriFluxServer) -> None:
    payload = await avail(server, sites=["US-Ha1", "CA-Let"], products=["BASE-BADM", "FLUXNET"])
    rows = rows_by(payload)
    assert rows[("CA-Let", "BASE-BADM")]["policy"] == "LEGACY"
    assert rows[("US-Ha1", "BASE-BADM")]["policy"] == "CCBY4.0"
    empty = {(e["siteId"], e["product"]): e["reason"] for e in payload["emptySites"]}
    assert "CC-BY-4.0 only" in empty[("CA-Let", "FLUXNET")]
    assert any("CC-BY-4.0 sites" in n for n in payload["notes"])
    verdict = {v["product"]: v for v in payload["policyVerdict"]}
    assert verdict["BASE-BADM"]["code"] == "LEGACY" and "CA-Let" in verdict["BASE-BADM"]["reason"]
    assert verdict["FLUXNET"]["code"] == "CCBY4.0"
    texts = " ".join(o["text"] for o in payload["combinedObligations"])
    assert "data portal" in texts and "ERA5" in texts


async def test_ccby_only_drops_legacy_and_tier2_only(server: AmeriFluxServer) -> None:
    payload = await avail(
        server,
        sites=["US-Ha1", "CA-Let", "RU-Sam"],
        products=["BASE-BADM", "FLUXNET2015"],
        policy="CC-BY-4.0",
    )
    rows = rows_by(payload)
    assert set(rows) == {("US-Ha1", "BASE-BADM"), ("US-Ha1", "FLUXNET2015")}
    empty = {(e["siteId"], e["product"]): e["reason"] for e in payload["emptySites"]}
    assert "not CC-BY-4.0" in empty[("CA-Let", "BASE-BADM")]
    assert "Tier Two only" in empty[("RU-Sam", "FLUXNET2015")]
    assert "not part of" in empty[("CA-Let", "FLUXNET2015")]


async def test_legacy_is_the_superset(server: AmeriFluxServer) -> None:
    ccby = await avail(server, products=["BASE-BADM"], policy="CCBY4.0", limit=200)
    legacy = await avail(server, products=["BASE-BADM"], policy="LEGACY", limit=200)
    ccby_sites = {r["siteId"] for r in ccby["rows"]}
    legacy_sites = {r["siteId"] for r in legacy["rows"]}
    assert ccby_sites < legacy_sites and "CA-Let" in legacy_sites - ccby_sites
    assert {r["policy"] for r in legacy["rows"]} == {"LEGACY"}
    assert any("no policy verdict" in n for n in legacy["notes"])


async def test_tier2_superset_and_labels(server: AmeriFluxServer) -> None:
    payload = await avail(server, products=["FLUXNET2015"], limit=200)
    labels = {r["siteId"]: r["policy"] for r in payload["rows"]}
    assert labels["RU-Sam"] == "TIER2" and labels["US-Ha1"] == "CCBY4.0"


async def test_bif_membership_has_no_years(server: AmeriFluxServer) -> None:
    payload = await avail(server, sites=["US-Ha1", "CA-Let"], products=["BIF"])
    rows = rows_by(payload)
    assert rows[("US-Ha1", "BIF")] == {
        "siteId": "US-Ha1",
        "product": "BIF",
        "policy": "CCBY4.0",
        "membership": True,
    }
    assert rows[("CA-Let", "BIF")]["policy"] == "LEGACY"
    assert any("membership only" in n for n in payload["notes"])


async def test_year_window(server: AmeriFluxServer) -> None:
    payload = await avail(
        server, sites=["US-Ha1", "US-xSR"], products=["BASE-BADM"], years="1995-1996"
    )
    rows = rows_by(payload)
    assert rows[("US-Ha1", "BASE-BADM")]["years"] == "1995-1996"
    empty = {(e["siteId"], e["product"]): e["reason"] for e in payload["emptySites"]}
    assert empty[("US-xSR", "BASE-BADM")] == "no data in 1995-1996"


async def test_resolution_and_paging(server: AmeriFluxServer) -> None:
    payload = await avail(server, sites=["SRER", "DK-ZaF"])
    assert {r["code"] for r in payload["resolved"]} == {"US-xSR", "GL-ZaF"}
    assert {(r["siteId"], r["product"]) for r in payload["rows"]} >= {
        ("US-xSR", "BASE-BADM"),
        ("GL-ZaF", "FLUXNET2015"),
    }
    paged = await avail(server, products=["BASE-BADM"], limit=3)
    assert len(paged["rows"]) == 3 and paged["page"]["nextOffset"] == 3


async def test_reads_are_cached(server: AmeriFluxServer, router: FixtureRouter) -> None:
    await avail(server, sites=["US-Ha1"], products=["BASE-BADM"])
    before = len(router.calls)
    again = await avail(server, sites=["US-Ha1"], products=["BASE-BADM"])
    assert len(router.calls) == before and again["source"]["cached"] is True


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        ({"products": ["BASE-BADM"], "policy": "Tier2"}, "invalid_combination"),
        ({"products": ["FLUXNET"], "policy": "LEGACY"}, "fluxnet_requires_ccby"),
        ({"products": ["FLUXNET2015"], "policy": "LEGACY"}, "invalid_combination"),
    ],
)
async def test_invalid_pairs_fail_before_any_request(
    server: AmeriFluxServer, router: FixtureRouter, args: dict[str, Any], reason: str
) -> None:
    error = await call_err(server, "amf_get_availability", args, "invalid_argument")
    assert error["details"]["reason"] == reason
    assert router.calls == []


async def test_policy_fitting_no_default_product(server: AmeriFluxServer) -> None:
    error = await call_err(
        server, "amf_get_availability", {"sites": ["CA-Let"], "policy": "TIER2"}, "invalid_argument"
    )
    assert error["details"]["reason"] == "invalid_combination"
    ok = await avail(server, sites=["US-Ha1"], policy="TIER2")  # FLUXNET2015 is a default here
    assert {r["product"] for r in ok["rows"]} == {"FLUXNET2015"}


async def test_no_emails_anywhere(server: AmeriFluxServer) -> None:
    payload = await avail(server, sites=["US-Ha1", "CA-Let"])
    assert "@" not in json.dumps(payload)


async def test_defaulted_products_skip_collection_noise(server: AmeriFluxServer) -> None:
    payload = await avail(server, sites=["US-Ha1", "CA-Let", "RU-Sam"])
    reasons = [e["reason"] for e in payload["emptySites"]]
    assert not any(r.startswith("not part of") for r in reasons)
    assert any("CC-BY-4.0 only" in r for r in reasons)  # CA-Let has no FLUXNET product
    explicit = await avail(server, sites=["RU-Sam"], products=["BASE-BADM"])
    assert explicit["emptySites"][0]["reason"].startswith("not part of")
