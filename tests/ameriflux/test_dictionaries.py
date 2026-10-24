"""Variable dictionaries: the build script's parsers, the committed files, the loaders."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from ameriflux_mcp.ameriflux.variables.dictionaries import (
    RESOLUTIONS,
    STATIC_DIR,
    fluxnet_dictionary,
    fluxnet_sources,
    fp_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_variable_dictionaries", ROOT / "scripts" / "build_variable_dictionaries.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FULLSET = """Variable,Units,Description
TIMEKEEPING,,
TIMESTAMP,YYYYMMDDHHMM,ISO timestamp - short format
,,
NET ECOSYSTEM EXCHANGE,,
NEE_VUT_REF,,"Net Ecosystem Exchange, VUT, reference"
HH,µmolCO2 m-2 s-1,
DD,gC m-2 d-1,calculated from half-hourly data
WW-MM,gC m-2 d-1,average from daily data
YY,gC m-2 y-1,sum from daily data
NEE_VUT_REF_NIGHT,,Average nighttime NEE_VUT_REF
HH,,not available
DD-YY,µmolCO2 m-2 s-1,average from half-hourly data
RECO_SR,,Ecosystem Respiration from Sundown Respiration
HH-YY,gC m-2 d-1,
"""
SUBSET = """Variable,Units,Description
NET ECOSYSTEM EXCHANGE,,
NEE_VUT_REF,,"Net Ecosystem Exchange, VUT, reference"
HH,µmolCO2 m-2 s-1,
"""
VAR_INFO = {
    "hh": "Variable||Units||Description||Members\nNEE_VUT_REF||�molCO2 m-2 s-1||NEE||(FC)(NEE)\n",
    "dd": "Variable||Units||Description||Members\nTIMESTAMP||YYYYMMDD||Day||\nNEE_VUT_REF||gC m-2 d-1||NEE||\n",
    "ww": "Variable||Units||Description||Members\n",
    "mm": "Variable||Units||Description||Members\nTIMESTAMP||YYYYMM||Month||\n",
    "yy": "Variable||Units||Description||Members\nTIMESTAMP||YYYY||Year||\nTA_F||adimensional||x||\n",
}


def test_unit_and_label_helpers(builder: ModuleType) -> None:
    assert builder.fix_units("�molCO2 m-2 s-1") == "µmolCO2 m-2 s-1"
    assert builder.fix_units("adimensional") == "nondimensional"
    assert builder.fix_units("  ") is None
    assert builder.expand("WW-YY") == ["WW", "MM", "YY"]
    assert builder.expand("DD") == ["DD"] and builder.expand("TA") == []


def test_build_fluxnet(builder: ModuleType) -> None:
    data = builder.build_fluxnet(FULLSET, SUBSET, VAR_INFO, {"fullset": {}})
    by_name = {v["name"]: v for v in data["variables"]}
    nee = by_name["NEE_VUT_REF"]
    assert nee["section"] == "NET ECOSYSTEM EXCHANGE" and nee["subset"] and nee["fullset"]
    assert nee["units"] == {
        "HH": "µmolCO2 m-2 s-1",
        "DD": "gC m-2 d-1",
        "WW": "gC m-2 d-1",
        "MM": "gC m-2 d-1",
        "YY": "gC m-2 y-1",
    }
    assert nee["notes"]["YY"] == "sum from daily data" and nee["members"] == "(FC)(NEE)"
    assert nee["oneflux"] == ["HH", "DD"]
    night = by_name["NEE_VUT_REF_NIGHT"]
    assert night["units"]["HH"] is None and night["notes"]["HH"] == "not available"
    assert by_name["RECO_SR"]["oneflux"] == [] and not by_name["RECO_SR"]["subset"]
    timestamp = by_name["TIMESTAMP"]
    assert timestamp["units"] == {
        "HH": None,
        "DD": "YYYYMMDD",
        "WW": None,
        "MM": "YYYYMM",
        "YY": "YYYY",
    }
    assert by_name["TA_F"]["units"]["YY"] == "nondimensional"  # ONEFlux-only name
    assert data["count"] == len(data["variables"])


def test_committed_files(builder: ModuleType) -> None:
    assert builder.check() == 0
    text = (STATIC_DIR / "fluxnet-variables.json").read_text(encoding="utf-8")
    assert "�" not in text
    data = json.loads(text)
    names = {v["name"] for v in data["variables"]}
    subset = {v["name"] for v in data["variables"] if v["subset"]}
    fullset = {v["name"] for v in data["variables"] if v["fullset"]}
    assert subset <= fullset and len(fullset) == 232 and len(subset) == 72
    assert all(list(v["units"]) == list(RESOLUTIONS) for v in data["variables"])
    assert {"NEE_VUT_XX", "TS_F_MDS_#", "SWC_F_MDS_#_QC"} <= names
    assert data["sources"]["fullset"]["etag"] == '"10afb-5a4e12f9d7b40"'


def test_loaders() -> None:
    fluxnet = fluxnet_dictionary()
    nee = fluxnet["NEE_VUT_REF"]
    assert nee.units["HH"] == "µmolCO2 m-2 s-1" and nee.available_at("YY")
    night = fluxnet["NEE_VUT_REF_NIGHT"]
    assert not night.available_at("HH") and night.available_at("DD")
    assert fluxnet["RECO_SR"].oneflux == ()
    assert fluxnet_sources()["oneflux"]["commit"].startswith("d4ecebe")
    snapshot = fp_snapshot()
    assert not snapshot.live and snapshot.fetched == "2026-10-24"
    by_name = snapshot.by_name()
    assert by_name["SWC"].height_direction == "neg" and by_name["FC"].max == 100.0
