from __future__ import annotations

import json
import re
from typing import Any

import pytest

from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.instructions import SERVER_INSTRUCTIONS
from ameriflux_mcp.prompts import PROMPTS, get_prompt, list_prompts
from ameriflux_mcp.registry import get_registered_tools
from ameriflux_mcp.resources import (
    DERIVED_TTL_MS,
    STATIC_DIR,
    STATIC_TTL_MS,
    list_resource_templates,
    list_resources,
    read_resource,
)
from ameriflux_mcp.server import AmeriFluxServer
from tests.fixture_router import Reply

#: The v0.1 tool surface (DESIGN.md "Tool surface"); text may name planned tools.
PLANNED_TOOLS = {
    "amf_ping",
    "amf_search_sites",
    "amf_get_site",
    "amf_get_availability",
    "amf_search_variables",
    "amf_describe_variables",
    "amf_get_citation",
    "amf_get_badm",
    "amf_download_data",
    "amf_list_files",
    "amf_preview_data",
    "amf_read_bif",
}


def test_listing_is_sorted_and_tagged() -> None:
    resources = list_resources()
    uris = [str(r.uri) for r in resources]
    assert uris == sorted(uris)
    assert uris == [
        "ameriflux://guide/data-policy",
        "ameriflux://guide/identity",
        "ameriflux://guide/variable-grammar",
        "ameriflux://reference/acknowledgments",
        "ameriflux://reference/fluxnet-variables",
        "ameriflux://reference/fp-variables",
        "ameriflux://reference/lter-crosswalk",
        "ameriflux://reference/neon-crosswalk",
        "ameriflux://reference/vocabularies",
    ]
    kinds = {str(r.uri): (r.meta or {})["io.ameriflux-mcp/kind"] for r in resources}
    assert kinds["ameriflux://reference/neon-crosswalk"] == "derived"
    assert kinds["ameriflux://reference/fp-variables"] == "derived"
    assert kinds["ameriflux://reference/vocabularies"] == "static"
    assert kinds["ameriflux://reference/fluxnet-variables"] == "static"
    assert [t.uri_template for t in list_resource_templates()] == ["ameriflux://site/{site_id}"]


async def test_reference_resources(server: AmeriFluxServer) -> None:
    ctx = server.tool_context("resources/read")
    vocab = json.loads((await read_resource("ameriflux://reference/vocabularies", ctx)).text)
    assert vocab["igbp"]["DBF"].startswith("Deciduous Broadleaf Forests")
    assert len(vocab["igbp"]) == 17 and "Dfb" in vocab["koeppen"]
    assert "swapped" in vocab["koeppenCaveats"]["Bsk"]
    assert vocab["products"]["FLUXNET"]["policies"] == ["CCBY4.0"]
    assert [u["code"] for u in vocab["intendedUse"]] == [1, 2, 3, 4, 5, 6]
    lter = json.loads((await read_resource("ameriflux://reference/lter-crosswalk", ctx)).text)
    assert lter["status"] == "draft"
    by_site = {r["siteId"]: r for r in lter["rows"]}
    assert by_site["US-Ha1"]["ediScope"] == "knb-lter-hfr"
    assert by_site["US-Seg"]["basis"] == "name" and by_site["US-Wjs"]["ediScope"] is None
    neon = await read_resource("ameriflux://reference/neon-crosswalk", ctx)
    assert neon.kind == "derived" and neon.cache_scope == "public"
    walk = json.loads(neon.text)
    assert walk["neonDataProduct"] == "DP4.00200.001"
    assert {r["neonSiteCode"]: r["siteId"] for r in walk["sites"]} == {
        "GUAN": "PR-xGU",
        "SRER": "US-xSR",
    }


async def test_site_template(server: AmeriFluxServer) -> None:
    ctx = server.tool_context("resources/read")
    card = await read_resource("ameriflux://site/SRER", ctx)
    payload = json.loads(card.text)
    assert payload["siteId"] == "US-xSR" and card.ttl_ms == DERIVED_TTL_MS
    with pytest.raises(ToolError) as missing:
        await read_resource("ameriflux://site/US-Ha9", ctx)
    assert missing.value.code == "not_found"


async def test_variable_and_policy_references(server: AmeriFluxServer) -> None:
    ctx = server.tool_context("resources/read")
    fp = json.loads((await read_resource("ameriflux://reference/fp-variables", ctx)).text)
    assert fp["source"] == "live" and fp["count"] == len(fp["variables"]) >= 100
    fc = next(v for v in fp["variables"] if v["name"] == "FC")
    assert fc["units"] == "µmolCO2 m-2 s-1" and fc["min"] == -100.0
    fluxnet = json.loads((await read_resource("ameriflux://reference/fluxnet-variables", ctx)).text)
    by_name = {v["name"]: v for v in fluxnet["variables"]}
    assert by_name["NEE_VUT_REF"]["units"]["YY"] == "gC m-2 y-1"
    assert fluxnet["sources"]["oneflux"]["commit"].startswith("d4ecebe")
    acks = json.loads((await read_resource("ameriflux://reference/acknowledgments", ctx)).text)
    texts = {t["key"]: t["text"] for t in acks["texts"]}
    assert "data service" in texts["doe_data_service"] and "data portal" in texts["doe_data_portal"]
    assert "Tier Two" in acks["fluxnet2015"]["mixing"]
    for uri, phrases in {
        "ameriflux://guide/data-policy": ("CC-BY + Legacy = Legacy", "Tier Two", "RU-Sam"),
        "ameriflux://guide/variable-grammar": ("_H_V_R", "GPP_NT_VUT_REF", "gC m-2 d-1"),
    }.items():
        text = (await read_resource(uri, ctx)).text
        for phrase in phrases:
            assert phrase in text, (uri, phrase)


async def test_fp_variables_falls_back_to_snapshot(server: AmeriFluxServer, router: Any) -> None:
    router.add("GET amfcdn.lbl.gov/api/v1/fp_var?limits=True", Reply(503, b"down", "text/plain"))
    ctx = server.tool_context("resources/read")
    fp = json.loads((await read_resource("ameriflux://reference/fp-variables", ctx)).text)
    assert fp["source"].startswith("snapshot ") and "snapshot" in fp["notes"][0]
    assert any(v["name"] == "FCH4" for v in fp["variables"])


async def test_identity_guide(server: AmeriFluxServer) -> None:
    ctx = server.tool_context("resources/read")
    content = await read_resource("ameriflux://guide/identity", ctx)
    assert content.ttl_ms == STATIC_TTL_MS and content.cache_scope == "public"
    for phrase in (
        "principal investigators (PIs)",
        "AMERIFLUX_USER_ID",
        "AMERIFLUX_USER_EMAIL",
        "AMERIFLUX_MCP_IDENTITY__IS_TEST",
        "confirm=true",
        "amfcdn.lbl.gov/create",
        "auth_required",
        "never accepts",
    ):
        assert phrase in content.text, phrase


async def test_unknown_resource_suggests(server: AmeriFluxServer) -> None:
    ctx = server.tool_context("resources/read")
    with pytest.raises(ToolError) as exc:
        await read_resource("ameriflux://guide/identiy", ctx)
    assert exc.value.code == "not_found"
    assert "ameriflux://guide/identity" in exc.value.details["didYouMean"]


def test_instructions() -> None:
    assert len(SERVER_INSTRUCTIONS) <= 1200
    for phrase in (
        "amf_search_sites",
        "amf_ping",
        "auth_required",
        "ameriflux://guide/identity",
        "confirm=true",
        "never invent",
        "DOI",
    ):
        assert phrase in SERVER_INSTRUCTIONS, phrase


def test_prompts_are_empty_until_step_8() -> None:
    assert PROMPTS == () and list_prompts() == []
    with pytest.raises(ToolError) as exc:
        get_prompt("find_flux_sites")
    assert exc.value.code == "not_found"


_TOOL_NAME_RE = re.compile(r"\bamf_[a-z_]+\b")


def test_text_names_only_planned_tools() -> None:
    registered = {spec.name for spec in get_registered_tools(transport="stdio")}
    assert registered <= PLANNED_TOOLS
    texts = {f.name: f.read_text(encoding="utf-8") for f in STATIC_DIR.glob("*.md")}
    texts["instructions"] = SERVER_INSTRUCTIONS
    for label, text in texts.items():
        unknown = set(_TOOL_NAME_RE.findall(text)) - PLANNED_TOOLS
        assert not unknown, f"{label} names unknown tools {sorted(unknown)}"
