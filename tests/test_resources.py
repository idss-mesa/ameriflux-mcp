from __future__ import annotations

import re

import pytest

from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.instructions import SERVER_INSTRUCTIONS
from ameriflux_mcp.prompts import PROMPTS, get_prompt, list_prompts
from ameriflux_mcp.registry import get_registered_tools
from ameriflux_mcp.resources import (
    STATIC_DIR,
    STATIC_TTL_MS,
    list_resource_templates,
    list_resources,
    read_resource,
)
from ameriflux_mcp.server import AmeriFluxServer

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
    assert uris == sorted(uris) == ["ameriflux://guide/identity"]
    assert all((r.meta or {})["io.ameriflux-mcp/kind"] == "static" for r in resources)
    assert list_resource_templates() == []


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
