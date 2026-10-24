"""amf_search_variables and amf_describe_variables against the recorded fixtures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import call_err, call_ok

HEIGHTS_PAGE = "GET ameriflux.lbl.gov/data/measurement-height/"


async def search(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_search_variables", args)


async def describe(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_describe_variables", args)


def names(payload: dict[str, Any]) -> list[str]:
    return [v["name"] for v in payload["variables"]]


@pytest.fixture
def quick_server(make_server: Callable[..., AmeriFluxServer], config: Config) -> AmeriFluxServer:
    """One attempt per upstream call, so failure paths do not sleep through retries."""
    cfg = config.model_copy(deep=True)
    cfg.upstream.retries.max_attempts = 1
    return make_server(config=cfg)


# ---------------------------------------------------------------------- search


async def test_search_words_across_dictionaries(server: AmeriFluxServer) -> None:
    payload = await search(server, query="soil temperature")
    assert names(payload) == ["TS", "TS_F_MDS_#"]
    ts = payload["variables"][0]
    assert ts["dictionary"] == ["fp"] and ts["units"] == "deg C"
    assert ts["plausibleRange"] == {"min": -40.0, "max": 65.0}
    fluxnet = payload["variables"][1]
    assert fluxnet["dictionary"] == ["fluxnet", "fluxnet_fullset", "fluxnet_subset"]
    assert fluxnet["inSubset"] is True and set(fluxnet["unitsByResolution"]) == {
        "HH",
        "DD",
        "WW",
        "MM",
        "YY",
    }
    assert any("XX stands for a percentile" in n for n in payload["notes"])


async def test_search_resolution_and_subset(server: AmeriFluxServer, router: FixtureRouter) -> None:
    payload = await search(server, query="GPP", dictionary="fluxnet_subset", resolution="DD")
    assert names(payload)[:2] == ["GPP_DT_VUT_REF", "GPP_DT_VUT_XX"]
    assert all(v["units"] == "gC m-2 d-1" for v in payload["variables"])
    assert all("fluxnet_subset" in v["dictionary"] for v in payload["variables"])
    assert router.calls == []  # FLUXNET dictionaries are bundled
    hourly = await search(server, query="NEE_VUT_REF_NIGHT", dictionary="fluxnet", resolution="hr")
    assert "NEE_VUT_REF_NIGHT" not in names(hourly)  # not available at HH


async def test_search_categories_and_facets(server: AmeriFluxServer) -> None:
    gases = await search(server, dictionary="fp", category="gas", limit=200)
    assert "FCH4" in names(gases) and set(gases["facets"]["category"]) == {"GASES"}
    sundown = await search(server, dictionary="fluxnet_fullset", category="sundown")
    assert names(sundown) == ["RECO_SR", "RECO_SR_N"]
    assert "fluxnet" not in sundown["variables"][0]["dictionary"]  # not in ONEFlux v1.3


async def test_search_paging_and_nothing(server: AmeriFluxServer) -> None:
    first = await search(server, limit=5)
    assert len(first["variables"]) == 5 and first["page"]["nextOffset"] == 5
    assert any("offset=5" in s for s in first["nextSteps"])
    none = await search(server, query="zzzqqq")
    assert none["variables"] == [] and any("No variable matches" in n for n in none["notes"])


async def test_search_rejects_bad_resolution(server: AmeriFluxServer) -> None:
    await call_err(
        server, "amf_search_variables", {"resolution": "fortnightly"}, "invalid_argument"
    )


# ---------------------------------------------------------------------- describe


async def test_describe_fluxnet_names_at_a_resolution(server: AmeriFluxServer) -> None:
    payload = await describe(
        server, names=["GPP_NT_VUT_REF", "NEE_VUT_05", "TS_F_MDS_2", "TA_F_MDS_QC"], resolution="DD"
    )
    by = {v["name"]: v for v in payload["variables"]}
    gpp = by["GPP_NT_VUT_REF"]
    assert gpp["grammar"] == "fluxnet" and gpp["units"] == "gC m-2 d-1"
    assert [q["kind"] for q in gpp["qualifiers"]] == ["partitioning", "ustar", "realization"]
    assert gpp["signConvention"].startswith("GPP is positive")
    assert gpp["base"]["name"] == "GPP"
    assert by["NEE_VUT_05"]["fluxnet"]["template"] == "NEE_VUT_XX"
    assert by["TS_F_MDS_2"]["fluxnet"]["template"] == "TS_F_MDS_#"
    qc = by["TA_F_MDS_QC"]["fluxnet"]
    assert qc["notesByResolution"] == {
        "DD": "fraction between 0-1, indicating percentage of measured and good quality gapfill data"
    }
    assert "signConvention" not in by["TA_F_MDS_QC"]
    assert any("ONEFlux d4ecebe" in n for n in payload["notes"])


async def test_describe_qc_changes_with_resolution(server: AmeriFluxServer) -> None:
    hh = await describe(server, names=["TA_F_MDS_QC"], resolution="HH")
    notes = hh["variables"][0]["fluxnet"]["notesByResolution"]
    assert notes == {"HH": "0 = measured; 1 = good quality gapfill; 2 = medium; 3 = poor"}
    every = await describe(server, names=["NEE_VUT_REF"])
    units = every["variables"][0]["fluxnet"]["unitsByResolution"]
    assert units["HH"] == "µmolCO2 m-2 s-1" and units["YY"] == "gC m-2 y-1"
    assert "units" not in every["variables"][0]


async def test_describe_base_names(server: AmeriFluxServer) -> None:
    payload = await describe(
        server, names=["FC_PI_F_1_1_A", "ta_f_1_1_1", "SWC_1_1_1_N", "TA_QC", "TA_F", "FETCH_70"]
    )
    by = {v["name"]: v for v in payload["variables"]}
    fc = by["FC_PI_F_1_1_A"]
    assert fc["grammar"] == "base" and fc["position"] == {
        "kind": "replicate_average",
        "h": 1,
        "v": 1,
    }
    assert fc["units"] == "µmolCO2 m-2 s-1" and "uptake" in fc["signConvention"]
    assert by["TA_F_1_1_1"]["position"]["kind"] == "sensor"
    assert by["TA_QC"]["units"] == "nondimensional (quality flag)"
    ta_f = by["TA_F"]
    assert ta_f["grammar"] == "base" and ta_f["fluxnet"]["template"] == "TA_F"
    assert any("also a FLUXNET name" in n for n in ta_f["notes"])
    assert by["FETCH_70"]["base"]["units"] == "m" and by["FETCH_70"]["notes"]


async def test_describe_unknown_names(server: AmeriFluxServer) -> None:
    payload = await describe(server, names=["TA_F_MDS_Q", "BOGUS_X"])
    by = {v["name"]: v for v in payload["variables"]}
    assert (
        by["TA_F_MDS_Q"]["recognized"] is False and "TA_F_MDS_QC" in by["TA_F_MDS_Q"]["didYouMean"]
    )
    assert by["BOGUS_X"]["grammar"] == "unknown" and by["BOGUS_X"]["unknownTokens"] == ["X"]
    assert any("Not recognized" in n for n in payload["notes"])
    assert any("amf_search_variables" in s for s in payload["nextSteps"])


async def test_describe_at_a_site(server: AmeriFluxServer) -> None:
    payload = await describe(server, names=["TA", "TA_1_2_1", "FCH4"], site="us-ha1")
    by = {v["name"]: v for v in payload["variables"]}
    ta = by["TA"]["atSite"]
    assert ta["siteId"] == "US-Ha1" and ta["inBaseVariables"] is True
    heights = {h["variable"]: h for h in ta["heights"]}
    assert heights["TA_1_1_1"]["heightM"] == 27.9 and heights["TA_1_1_1"]["instrument"]
    assert ta["heightsFile"].endswith("BASE_MeasurementHeight_20260908.csv")
    cover = {c["variable"]: c for c in ta["coverage"]}
    assert cover["TA_1_1_1"]["years"].startswith("1991") and ta["coverageSnapshot"] == "2025-10-20"
    one = by["TA_1_2_1"]["atSite"]
    assert [h["variable"] for h in one["heights"]] == ["TA_1_2_1"]  # that sensor only
    assert by["FCH4"]["atSite"]["inBaseVariables"] is False
    assert any("snapshot of 2025-10-20" in n for n in payload["notes"])
    assert payload["source"]["backend"] == "mixed"
    assert "atSite" in payload["source"]["derived"]


async def test_describe_at_a_fluxnet_only_site(
    server: AmeriFluxServer, router: FixtureRouter
) -> None:
    payload = await describe(server, names=["TA"], site="DE-Tha")
    assert any("not an AmeriFlux site" in n for n in payload["notes"])
    assert "heights" not in payload["variables"][0]["atSite"]
    assert not router.calls_to("/data/measurement-height/")


async def test_describe_survives_missing_sources(
    quick_server: AmeriFluxServer, router: FixtureRouter
) -> None:
    router.add(HEIGHTS_PAGE, Reply(503, b"down", "text/html"))
    router.add("GET amfcdn.lbl.gov/api/v1/fp_var?limits=True", Reply(503, b"down", "text/plain"))
    payload = await describe(quick_server, names=["TA"], site="US-Ha1")
    assert any("Measurement heights unavailable" in n for n in payload["notes"])
    assert any("bundled snapshot of 2026-10-24" in n for n in payload["notes"])
    assert payload["variables"][0]["base"]["units"] == "deg C"
    assert payload["variables"][0]["atSite"]["coverage"]


async def test_describe_rejects_bad_input(server: AmeriFluxServer) -> None:
    await call_err(server, "amf_describe_variables", {"names": []}, "invalid_argument")
    too_many = {"names": [f"TA_{i}" for i in range(21)]}
    await call_err(server, "amf_describe_variables", too_many, "invalid_argument")
    await call_err(
        server, "amf_describe_variables", {"names": ["TA"], "resolution": "XX"}, "invalid_argument"
    )
