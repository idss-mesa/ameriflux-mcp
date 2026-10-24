"""amf_search_sites and amf_get_site against the recorded fixtures (15 fixture sites)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests.helpers import call_err, call_ok


async def search(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_search_sites", args)


def ids(payload: dict[str, Any]) -> list[str]:
    return [s["siteId"] for s in payload["sites"]]


# ---------------------------------------------------------------------- search


async def test_search_everything_and_facets(server: AmeriFluxServer) -> None:
    payload = await search(server, limit=200)
    assert len(ids(payload)) == 15 and ids(payload) == sorted(ids(payload))
    assert payload["page"]["total"] == 15 and payload["page"]["truncated"] is False
    facets = payload["facets"]
    assert facets["collection"]["ameriflux"] == 12 and facets["collection"]["fluxnet2015"] == 7
    assert facets["policy"]["LEGACY"] == 1 and facets["policy"]["TIER2"] == 1


async def test_search_summary_fields(server: AmeriFluxServer) -> None:
    ha1 = next(s for s in (await search(server, query="US-Ha1"))["sites"])
    assert ha1["siteId"] == "US-Ha1" and ha1["igbp"] == "DBF" and ha1["state"] == "MA"
    assert ha1["products"]["base"]["first"] == 1991
    assert ha1["products"]["fluxnet2015"] == {"tier": "CCBY4.0", "years": "1991-2012"}
    assert "LTER" in ha1["networks"] and "AmeriFlux" not in ha1["networks"]
    assert "@" not in json.dumps(ha1)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"query": "harvard"}, ["US-Ha1", "US-Ha2", "US-Ha3"]),
        ({"query": "harv forest swamp"}, ["US-Ha3"]),
        ({"query": "srer"}, ["US-xSR"]),
        ({"collection": "fluxnet_ch4"}, ["US-CRT", "US-Myb"]),
        ({"collection": "fluxnet2015", "policy": "Tier2"}, ["RU-Sam"]),
        ({"policy": "Legacy"}, ["CA-Let"]),
        ({"product": "FLUXNET2015", "country": ["US"]}, ["US-CRT", "US-Ha1", "US-Myb"]),
        ({"igbp": ["dbf"], "state": ["ma"]}, ["US-Ha1"]),
        ({"igbp": ["ENF", "WET"], "state": ["MA"]}, ["US-Ha2", "US-Ha3"]),
        ({"network": ["NEON"]}, ["PR-xGU", "US-xSR"]),
        ({"country": ["Canada"]}, ["CA-Let"]),
        ({"koeppen": ["B"], "country": ["US"]}, ["US-Jo2", "US-Seg", "US-xSR"]),
        ({"gas": ["CH4"], "collection": "ameriflux"}, ["US-CRT", "US-Ha3", "US-Myb"]),
        ({"bbox": [-112, 30, -104, 37]}, ["US-Jo2", "US-Seg", "US-xSR"]),
        ({"base_variable": ["FETCH_90"]}, ["PR-xGU", "US-Ha3", "US-Jo2", "US-xSR"]),
    ],
)
async def test_search_filters(
    server: AmeriFluxServer, args: dict[str, Any], expected: list[str]
) -> None:
    assert ids(await search(server, limit=200, **args)) == expected


async def test_search_years(server: AmeriFluxServer) -> None:
    old = await search(server, years="1991-1992", product="BASE-BADM", limit=200)
    assert ids(old) == ["US-Ha1"]
    long = await search(server, product="FLUXNET", min_years=20, limit=200)
    assert ids(long) == ["US-Ha1"]
    by_years = await search(server, product="BASE-BADM", sort="years", limit=3)
    assert ids(by_years)[0] == "US-Ha1"


async def test_search_near_sorts_by_distance(server: AmeriFluxServer) -> None:
    payload = await search(
        server, near={"latitude": 42.5, "longitude": -72.2, "radius_km": 50}, limit=200
    )
    assert ids(payload)[:3] == ["US-Ha1", "US-Ha2", "US-Ha3"] or set(ids(payload)) == {
        "US-Ha1",
        "US-Ha2",
        "US-Ha3",
    }
    distances = [s["distanceKm"] for s in payload["sites"]]
    assert distances == sorted(distances) and distances[-1] <= 50


async def test_search_paging_and_budget(server: AmeriFluxServer) -> None:
    first = await search(server, limit=5)
    assert len(first["sites"]) == 5 and first["page"]["nextOffset"] == 5
    assert any("offset=5" in step for step in first["nextSteps"])
    second = await search(server, limit=5, offset=5)
    assert not set(ids(first)) & set(ids(second))


async def test_search_nothing_matches(server: AmeriFluxServer) -> None:
    payload = await search(server, query="zzzzqqq")
    assert payload["sites"] == [] and payload["notes"]


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ({"product": "BIF"}, "invalid_argument"),
        ({"product": "FLUXNET", "policy": "LEGACY"}, "invalid_argument"),
        ({"product": "BASE", "policy": "TIER2"}, "invalid_argument"),
        ({"policy": "maybe"}, "invalid_argument"),
        ({"years": "next year"}, "invalid_argument"),
        ({"bbox": [10, 0, -10, 5]}, "invalid_argument"),
        ({"sort": "distance"}, "invalid_argument"),
        ({"bogus": 1}, "invalid_argument"),
    ],
)
async def test_search_rejects_bad_input_before_any_request(
    server: AmeriFluxServer, router: Any, args: dict[str, Any], code: str
) -> None:
    await call_err(server, "amf_search_sites", args, code)
    if "sort" not in args:  # sort is checked after the catalog loads
        assert router.calls == []


# ---------------------------------------------------------------------- get_site


async def test_get_site_full_card(server: AmeriFluxServer) -> None:
    site = await call_ok(server, "amf_get_site", {"site": "US-Ha1"})
    assert site["siteId"] == "US-Ha1" and site["resolved"] == []
    assert site["collections"] == ["ameriflux", "fluxnet2015"]
    assert site["ecosystem"]["igbpLabel"].startswith("Deciduous Broadleaf Forests")
    assert site["ecosystem"]["koeppen"] == "Dfb" and site["ecosystem"]["koeppenLabel"]
    assert site["policy"]["code"] == "CCBY4.0" and "CC-BY-4.0" in site["policy"]["meaning"]
    assert site["dois"] == {"base": "10.17190/AMF/1246059", "fluxnet": "10.17190/AMF/1871137"}
    assert site["tower"]["start"] == "1991" and "end" not in site["tower"]
    assert site["crosslinks"]["lter"] == {
        "lterSite": "HFR",
        "ediScope": "knb-lter-hfr",
        "basis": "tag",
        "status": "draft",
    }
    assert any("edi_search_packages(scope='knb-lter-hfr')" in s for s in site["nextSteps"])
    assert site["team"] and site["team"][0]["role"] == "PI" and site["teamTotal"] >= 1
    assert site["baseVariables"] and site["baseVariablesTotal"] == len(site["baseVariables"])
    assert "@" not in json.dumps(site)


async def test_get_site_neon_and_resolution(server: AmeriFluxServer) -> None:
    site = await call_ok(server, "amf_get_site", {"site": "SRER"})
    assert site["siteId"] == "US-xSR"
    assert site["resolved"] == [
        {"field": "site", "input": "SRER", "code": "US-xSR", "confidence": 1.0}
    ]
    assert site["crosslinks"]["neonSiteCode"] == "SRER"
    assert site["crosslinks"]["neonDataProduct"] == "DP4.00200.001"
    assert "fluxnetPage" not in site["crosslinks"]  # placeholder URL dropped
    assert any("neon_get_availability" in s for s in site["nextSteps"])


async def test_get_site_renamed_and_fluxnet_only(server: AmeriFluxServer) -> None:
    site = await call_ok(server, "amf_get_site", {"site": "DK-ZaF"})
    assert site["siteId"] == "GL-ZaF" and site["collections"] == ["fluxnet2015"]
    assert any("renamed GL-ZaF" in n for n in site["notes"])
    assert any("not an AmeriFlux site" in n for n in site["notes"])


async def test_get_site_legacy(server: AmeriFluxServer) -> None:
    site = await call_ok(server, "amf_get_site", {"site": "ca-let"})
    assert site["siteId"] == "CA-Let" and site["policy"]["code"] == "LEGACY"
    assert any("no FLUXNET product" in n for n in site["notes"])


async def test_get_site_koeppen_caveat(server: AmeriFluxServer) -> None:
    site = await call_ok(server, "amf_get_site", {"site": "US-xSR"})
    assert site["ecosystem"]["koeppen"] == "Bsk"
    assert "swapped" in site["ecosystem"]["koeppenNote"]


async def test_get_site_sections(server: AmeriFluxServer) -> None:
    site = await call_ok(server, "amf_get_site", {"site": "US-Ha1", "include": ["team"]})
    assert site["team"] and "baseVariables" not in site and "description" not in site


async def test_contacts_need_both_flags(
    server: AmeriFluxServer,
    make_server: Callable[..., AmeriFluxServer],
    config: Config,
    tmp_path: Path,
) -> None:
    asked = await call_ok(server, "amf_get_site", {"site": "US-Ha1", "include_contacts": True})
    assert all("email" not in m for m in asked["team"])
    assert any("withheld" in n for n in asked["notes"])
    cfg = config.model_copy(deep=True)
    cfg.privacy.allow_contact_emails = True
    cfg.cache.disk_dir = tmp_path / "fresh-cache"  # the shared disk cache never holds emails
    allowing = make_server(config=cfg)
    shown = await call_ok(allowing, "amf_get_site", {"site": "US-Ha1", "include_contacts": True})
    assert all(m["email"].endswith("@example.org") for m in shown["team"])
    hidden = await call_ok(allowing, "amf_get_site", {"site": "US-Ha1"})
    assert all("email" not in m for m in hidden["team"])


async def test_contacts_from_a_disk_loaded_catalog(
    server: AmeriFluxServer, make_server: Callable[..., AmeriFluxServer], config: Config
) -> None:
    await call_ok(server, "amf_get_site", {"site": "US-Ha1"})  # warms the shared disk cache
    cfg = config.model_copy(deep=True)
    cfg.privacy.allow_contact_emails = True
    restarted = make_server(config=cfg)
    site = await call_ok(restarted, "amf_get_site", {"site": "US-Ha1", "include_contacts": True})
    assert all("email" not in m for m in site["team"])
    assert any("disk cache" in n for n in site["notes"])


@pytest.mark.parametrize(
    ("site", "code"),
    [
        ("Harvard Forest", "ambiguous_input"),
        ("US-Ha9", "not_found"),
        ("AA-Flx", "invalid_argument"),
    ],
)
async def test_get_site_errors(server: AmeriFluxServer, site: str, code: str) -> None:
    error = await call_err(server, "amf_get_site", {"site": site}, code)
    if code == "ambiguous_input":
        assert {c["siteId"] for c in error["details"]["candidates"]} >= {
            "US-Ha1",
            "US-Ha2",
            "US-Ha3",
        }
