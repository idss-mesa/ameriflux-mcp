"""amf_list_files, amf_preview_data and amf_read_bif against synthetic local archives."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests import archives
from tests.fixture_router import FixtureRouter
from tests.helpers import call_err, call_ok

LOCAL_TOOLS = {"amf_list_files", "amf_preview_data", "amf_read_bif"}


@pytest.fixture
def downloads(config: Config) -> Path:
    path = config.downloads.directory
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def stocked(downloads: Path) -> Path:
    archives.base_badm_zip(downloads)
    archives.base_hr_zip(downloads / "older", "27-5")
    archives.base_hr_zip(downloads)
    archives.fluxnet_zip(downloads / "fluxnet")
    archives.fluxnet2015_subset_zip(downloads / "fluxnet2015")
    archives.hostile_zip(downloads / "odd")
    (downloads / "notes.txt").write_text("not ours")
    (downloads / "FLX_US-Myb_FLUXNET-CH4_HH_2010-2017_1-1.csv").write_text("TIMESTAMP_START\n")
    return downloads


async def preview(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_preview_data", args)


def cols(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in payload["columns"]}


# ---------------------------------------------------------------------- surface


async def test_local_tools_are_stdio_only(
    server: AmeriFluxServer, http_server: AmeriFluxServer
) -> None:
    stdio = {t.name for t in server.tool_definitions()}
    http = {t.name for t in http_server.tool_definitions()}
    assert stdio >= LOCAL_TOOLS and not LOCAL_TOOLS & http
    for tool in server.tool_definitions():
        if tool.name in LOCAL_TOOLS:
            assert tool.annotations and tool.annotations.open_world_hint is False
            assert tool.annotations.read_only_hint is True


# ---------------------------------------------------------------------- list


async def test_list_files(server: AmeriFluxServer, stocked: Path, router: FixtureRouter) -> None:
    payload = await call_ok(server, "amf_list_files", {})
    paths = [f["path"] for f in payload["files"]]
    assert "AMF_US-CRT_BASE-BADM_2-5.zip" in paths and "notes.txt" not in paths
    assert payload["unrecognized"] == 1 and payload["roots"] == [str(stocked)]
    by_path = {f["path"]: f for f in payload["files"]}
    flux = by_path["fluxnet/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip"]
    assert (
        flux["family"] == "fluxnet"
        and flux["years"] == "2012-2013"
        and flux["version"] == "v1.3_r1"
    )
    kinds = {m["name"]: m["kind"] for m in flux["members"]}
    assert kinds["AMF_AR-Bal_FLUXNET_FLUXMET_HH_2012-2013_v1.3_r1.csv"] == "data"
    assert kinds["AMF_AR-Bal_FLUXNET_BIF_2012-2013_v1.3_r1.csv"] == "bif"
    assert kinds["README.txt"] == "readme"
    aux = by_path["fluxnet2015/FLX_US-Ha1_FLUXNET2015_SUBSET_1991-2012_1-4.zip"]["members"]
    assert {m["kind"] for m in aux} == {"data", "aux_table"}
    odd = {
        m["name"]: m.get("refused") for m in by_path["odd/AMF_US-CRT_BASE-BADM_9-9.zip"]["members"]
    }
    assert odd["bomb.csv"] and odd["AMF_US-CRT_BIF_20990101.xlsx"] == "symbolic link"
    ch4 = by_path["FLX_US-Myb_FLUXNET-CH4_HH_2010-2017_1-1.csv"]
    assert "v0.2" in ch4["note"]
    assert payload["facets"]["family"]["base"] == 4
    assert router.calls == []  # local tools never go upstream


async def test_list_filters_and_paging(server: AmeriFluxServer, stocked: Path) -> None:
    flux = await call_ok(server, "amf_list_files", {"family": ["fluxnet2015"]})
    assert [f["path"] for f in flux["files"]] == [
        "fluxnet2015/FLX_US-Ha1_FLUXNET2015_SUBSET_1991-2012_1-4.zip"
    ]
    ha1 = await call_ok(server, "amf_list_files", {"site": "us-ha1", "include_members": False})
    assert {f["siteId"] for f in ha1["files"]} == {"US-Ha1"} and "members" not in ha1["files"][0]
    one = await call_ok(server, "amf_list_files", {"path": "fluxnet"})
    assert len(one["files"]) == 1
    archive = await call_ok(
        server, "amf_list_files", {"path": "fluxnet/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip"}
    )
    assert archive["files"][0]["membersTotal"] == 7
    page = await call_ok(server, "amf_list_files", {"limit": 2})
    assert page["page"]["nextOffset"] == 2 and any("offset=2" in s for s in page["nextSteps"])


async def test_list_with_no_folders(server: AmeriFluxServer) -> None:
    payload = await call_ok(server, "amf_list_files", {})
    assert payload["files"] == [] and any(
        "created by the first download" in n for n in payload["notes"]
    )
    await call_err(server, "amf_list_files", {"path": "/etc"}, "invalid_argument")


# ---------------------------------------------------------------------- preview


async def test_preview_base_zip_default_member(server: AmeriFluxServer, stocked: Path) -> None:
    payload = await preview(
        server, file="AMF_US-CRT_BASE-BADM_2-5.zip", columns=["TA", "FC", "G_1_1_1"]
    )
    info = payload["fileInfo"]
    assert info["member"] == "AMF_US-CRT_BASE_HH_2-5.csv" and info["family"] == "base"
    assert info["stepMinutes"] == 30 and info["timeRange"]["first"] == "2011-01-01T00:00"
    assert info["headerLines"] == ["# Site: US-CRT", "# Version: 2-5"]
    assert info["utcOffsets"] == [{"hours": -5.0, "siteId": "US-CRT"}]
    c = cols(payload)
    assert c["TA"]["units"] == "deg C" and c["TA"]["outOfRange"] == 0 and c["TA"]["count"] > 0
    assert c["FC"]["units"] == "µmolCO2 m-2 s-1" and c["FC"]["missing"] > 0
    assert payload["scan"]["statsScope"] == "window" and "rows" not in payload
    assert any("UTC offset from" in n for n in payload["notes"])
    assert any("amf_get_citation(sites=['US-CRT']" in s for s in payload["nextSteps"])


async def test_preview_hourly_base_rows_utc_and_ranges(
    server: AmeriFluxServer, stocked: Path
) -> None:
    summary = await preview(server, site="US-Ha1")
    assert "AMF_US-Ha1_BASE-BADM_28-5.zip" in summary["notes"][0]  # newest version wins
    c = cols(summary)
    assert c["TA_1_1_1"]["missing"] == 3 and c["FC"]["outOfRange"] == 1 and c["FC"]["max"] == 250.0
    assert summary["fileInfo"]["stepMinutes"] == 60 and summary["fileInfo"]["resolution"] == "HR"
    rows = await preview(
        server,
        site="US-Ha1",
        mode="rows",
        to_utc=True,
        columns=["TA_1_1_1"],
        start="2011-12-31T22:00",
        max_rows=4,
    )
    assert rows["rowColumns"] == [
        "TIMESTAMP_START_UTC",
        "TIMESTAMP_END_UTC",
        "TIMESTAMP_START",
        "TIMESTAMP_END",
        "TA_1_1_1",
    ]
    first, third = rows["rows"][0], rows["rows"][2]
    assert first[:3] == ["2012-01-01T03:00Z", "2012-01-01T04:00Z", "201112312200"]  # offset -5
    assert third[0] == "2012-01-01T06:00Z" and third[2] == "201201010000"  # offset -6 from 2012
    assert any("changed over time" in n for n in rows["notes"])
    assert rows["page"]["nextOffset"] == 4 and rows["scan"]["statsScope"] == "rows"


async def test_preview_fluxnet_hourly_hh_and_qc(server: AmeriFluxServer, stocked: Path) -> None:
    file = "fluxnet/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip"
    payload = await preview(server, file=file, qc_max=1)
    info = payload["fileInfo"]
    assert info["member"].startswith("AMF_AR-Bal_FLUXNET_FLUXMET_HH") and info["stepMinutes"] == 60
    assert any("ONEFlux v1.3 names the finest step HH" in n for n in payload["notes"])
    nee = cols(payload)["NEE_VUT_REF"]
    assert nee["qcFiltered"] == 24 and nee["units"] == "µmolCO2 m-2 s-1" and nee["outOfRange"] == 0
    assert info["utcOffsets"][0]["hours"] == -3.0
    daily = await preview(server, file=file, resolution="DD", qc_min_fraction=0.5)
    assert daily["fileInfo"]["resolution"] == "DD"
    assert cols(daily)["NEE_VUT_REF"]["units"] == "gC m-2 d-1"
    assert "outOfRange" not in cols(daily)["NEE_VUT_REF"]  # FP ranges are HH units
    await call_err(
        server, "amf_preview_data", {"file": file, "qc_min_fraction": 0.5}, "invalid_argument"
    )
    await call_err(
        server,
        "amf_preview_data",
        {"file": file, "resolution": "DD", "qc_max": 1},
        "invalid_argument",
    )


async def test_preview_subset_view(server: AmeriFluxServer, stocked: Path) -> None:
    file = "fluxnet/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip"
    payload = await preview(server, file=file, view="subset")
    names = set(cols(payload))
    assert {"NEE_VUT_REF", "GPP_NT_VUT_REF", "SW_IN_F", "P_F"} <= names
    assert not names & {"TA_F_MDS", "TA_ERA", "NEE_CUT_REF"}
    assert any("SUBSET view" in n for n in payload["notes"])
    await call_err(
        server,
        "amf_preview_data",
        {"file": "AMF_US-CRT_BASE-BADM_2-5.zip", "view": "subset"},
        "invalid_argument",
    )


async def test_preview_fluxnet2015_and_aux(server: AmeriFluxServer, stocked: Path) -> None:
    hr = await preview(server, site="US-Ha1", product="FLUXNET2015")
    assert hr["fileInfo"]["member"] == "FLX_US-Ha1_FLUXNET2015_SUBSET_HR_1991-2012_1-4.csv"
    assert any("No BIF beside this file" in n for n in hr["notes"])
    aux = await preview(
        server,
        file="fluxnet2015/FLX_US-Ha1_FLUXNET2015_SUBSET_1991-2012_1-4.zip::FLX_US-Ha1_FLUXNET2015_AUXMETEO_1991-2012_1-4.csv",
    )
    assert aux["fileInfo"]["kind"] == "aux_table" and "timeRange" not in aux["fileInfo"]
    assert cols(aux)["VARIABLE"]["textValues"] == ["TA", "PA"] and cols(aux)["VALUE"]["count"] == 3


async def test_preview_refusals(server: AmeriFluxServer, stocked: Path) -> None:
    async def err(args: dict[str, Any], code: str = "invalid_argument") -> dict[str, Any]:
        return await call_err(server, "amf_preview_data", args, code)

    assert await err({"file": "FLX_US-Myb_FLUXNET-CH4_HH_2010-2017_1-1.csv"}, "feature_unavailable")
    bif = await err({"file": "AMF_US-CRT_BASE-BADM_2-5.zip::AMF_US-CRT_BIF_20201005.xlsx"})
    assert bif["details"]["reason"] == "bif_file"
    bomb = await err({"file": "odd/AMF_US-CRT_BASE-BADM_9-9.zip::bomb.csv"})
    assert bomb["details"]["reason"] in ("unsafe_member", "unrecognized_name")
    slip = await err({"file": "odd/AMF_US-CRT_BASE-BADM_9-9.zip::../AMF_US-CRT_BASE_HR_9-9.csv"})
    assert slip["details"]["reason"] == "unsafe_member"
    assert (await err({"file": "notes.txt"}))["details"]["reason"] == "unrecognized_name"
    assert (await err({"file": "../x.csv"}))["details"]["reason"] == "outside_local_roots"
    assert (await err({}))["details"]["reason"] == "no_target"
    await err({"site": "US-Zzz"}, "not_found")
    await err({"file": "AMF_US-CRT_BASE-BADM_2-5.zip", "columns": ["NOPE"]})
    await err({"file": "AMF_US-CRT_BASE-BADM_2-5.zip", "start": "2013", "end": "2012"})


async def test_preview_budget(
    make_server: Callable[..., AmeriFluxServer], config: Config, downloads: Path
) -> None:
    from datetime import datetime, timedelta

    body = archives.series(datetime(2000, 1, 1), 6000, timedelta(minutes=30), ["TA"])
    (downloads / "AMF_US-Big_BASE_HH_1-1.csv").write_text(body)
    cfg = config.model_copy(deep=True)
    cfg.limits.preview_scan_max_bytes = 2048
    payload = await preview(make_server(config=cfg), file="AMF_US-Big_BASE_HH_1-1.csv")
    assert payload["scan"]["truncatedReason"] == "budget"
    assert any("budget" in n and "DD or MM" in n for n in payload["notes"])


# ---------------------------------------------------------------------- read_bif


async def test_read_bif_from_base_zip(server: AmeriFluxServer, stocked: Path) -> None:
    payload = await call_ok(server, "amf_read_bif", {"file": "AMF_US-CRT_BASE-BADM_2-5.zip"})
    info = payload["fileInfo"]
    assert info["member"] == "AMF_US-CRT_BIF_20201005.xlsx" and info["sites"] == ["US-CRT"]
    assert info["groups"]["GRP_UTC_OFFSET"] == 1
    assert payload["citations"] == [
        {
            "siteId": "US-CRT",
            "doi": "10.17190/AMF/1246156",
            "citation": "Jane Doe (2020), AmeriFlux BASE US-CRT, Ver. 2-5",
            "dataProduct": "AmeriFlux",
        }
    ]
    assert {a["source"] for a in payload["acknowledgments"]} == {
        "GRP_ACKNOWLEDGEMENT",
        "GRP_SITE_FUNDING",
    }
    assert payload["withheld"] == 5 and "@" not in json.dumps(payload["entries"])
    assert any("amf_get_citation gives the current one" in n for n in payload["notes"])


async def test_read_bif_offsets_groups_and_site(server: AmeriFluxServer, stocked: Path) -> None:
    payload = await call_ok(
        server, "amf_read_bif", {"site": "US-Ha1", "groups": ["grp_utc_offset"]}
    )
    assert [o["dateStart"] for o in payload["utcOffsets"]] == ["19910101", "20120101"]
    assert {e["group"] for e in payload["entries"]} == {"GRP_UTC_OFFSET"}
    flux = await call_ok(
        server, "amf_read_bif", {"file": "fluxnet/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip"}
    )
    assert flux["fileInfo"]["member"] == "AMF_AR-Bal_FLUXNET_BIF_2012-2013_v1.3_r1.csv"
    assert flux["utcOffsets"][0]["hours"] == -3.0
    none = await call_ok(
        server, "amf_read_bif", {"file": "AMF_US-CRT_BASE-BADM_2-5.zip", "site_id": "US-Zzz"}
    )
    assert none["entries"] == [] and any("No entries for US-Zzz" in n for n in none["notes"])
    await call_err(
        server,
        "amf_read_bif",
        {"file": "fluxnet2015/FLX_US-Ha1_FLUXNET2015_SUBSET_1991-2012_1-4.zip"},
        "not_found",
    )
    await call_err(
        server,
        "amf_read_bif",
        {"file": "AMF_US-CRT_BASE-BADM_2-5.zip::AMF_US-CRT_BASE_HH_2-5.csv"},
        "invalid_argument",
    )


async def test_read_bif_contacts_need_both_flags(
    make_server: Callable[..., AmeriFluxServer],
    config: Config,
    server: AmeriFluxServer,
    stocked: Path,
) -> None:
    asked = await call_ok(
        server, "amf_read_bif", {"file": "AMF_US-CRT_BASE-BADM_2-5.zip", "include_contacts": True}
    )
    assert asked["withheld"] == 5 and any("withheld" in n for n in asked["notes"])
    cfg = config.model_copy(deep=True)
    cfg.privacy.allow_contact_emails = True
    allowing = make_server(config=cfg)
    shown = await call_ok(
        allowing, "amf_read_bif", {"file": "AMF_US-CRT_BASE-BADM_2-5.zip", "include_contacts": True}
    )
    assert shown["withheld"] == 0 and "jane.doe@example.org" in json.dumps(shown["entries"])
    hidden = await call_ok(allowing, "amf_read_bif", {"file": "AMF_US-CRT_BASE-BADM_2-5.zip"})
    assert hidden["withheld"] == 5
