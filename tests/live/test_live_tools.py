"""Live smoke tests of each networked tool (opt-in: ``AMERIFLUX_MCP_LIVE=1``; GET only).

The nightly job has no identity and these calls never confirm a download:
``amf_download_data`` runs in plan mode, which only reads the catalog and availability,
and the test asserts no POST was made. Values are checked loosely (shapes, known
sentinels), so ordinary upstream growth does not fail the job.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer, create_server

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("AMERIFLUX_MCP_LIVE") != "1", reason="set AMERIFLUX_MCP_LIVE=1"
    ),
]


@pytest.fixture
async def live(tmp_path: Path) -> AsyncIterator[AmeriFluxServer]:
    config = Config.model_validate(
        {
            "downloads": {"directory": str(tmp_path / "downloads"), "enabled": True},
            "cache": {"disk_dir": str(tmp_path / "cache")},
        }
    )
    server = create_server(config, transport="stdio")
    yield server
    await server.aclose()


async def ok(server: AmeriFluxServer, name: str, args: dict[str, Any]) -> dict[str, Any]:
    outcome = await server.call(name, args)
    assert not outcome.is_error, outcome.payload
    payload: dict[str, Any] = outcome.payload
    assert not any(e.startswith("POST") for e in payload.get("source", {}).get("endpoints", []))
    return payload


async def test_discovery_tools(live: AmeriFluxServer) -> None:
    ping = await ok(live, "amf_ping", {"check_api": True})
    assert ping["upstream"]["ok"] is True
    found = await ok(
        live, "amf_search_sites", {"igbp": ["DBF"], "state": ["MA"], "product": "FLUXNET"}
    )
    assert "US-Ha1" in {s["siteId"] for s in found["sites"]}
    site = await ok(live, "amf_get_site", {"site": "SRER"})
    assert site["siteId"] == "US-xSR"
    avail = await ok(
        live, "amf_get_availability", {"sites": ["US-Ha1", "CA-Let"], "products": ["FLUXNET"]}
    )
    assert "CA-Let" in {e["siteId"] for e in avail["emptySites"]}


async def test_variable_tools(live: AmeriFluxServer) -> None:
    found = await ok(live, "amf_search_variables", {"query": "latent heat"})
    assert found["variables"]
    described = await ok(
        live,
        "amf_describe_variables",
        {"names": ["GPP_NT_VUT_REF", "TA_F_MDS_QC"], "resolution": "DD"},
    )
    assert described["variables"][0]["name"] == "GPP_NT_VUT_REF"


async def test_citation_tools(live: AmeriFluxServer) -> None:
    cite = await ok(live, "amf_get_citation", {"sites": ["US-Ha1"], "product": "BASE-BADM"})
    assert "Ver." in cite["citations"][0]["citation"]
    badm = await ok(live, "amf_get_badm", {"site": "US-Ha1"})
    assert badm["siteId"] == "US-Ha1"


async def test_download_plan_sends_nothing(live: AmeriFluxServer) -> None:
    plan = await ok(live, "amf_download_data", {"sites": ["AR-Bal"], "product": "FLUXNET"})
    assert plan["mode"] == "plan" and plan["eligible"][0]["siteId"] == "AR-Bal"
    assert plan["policy"]["code"] == "CCBY4.0"
