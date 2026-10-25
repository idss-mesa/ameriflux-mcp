"""The three prompts (build step 8): listing, rendering, validation, no stale names."""

from __future__ import annotations

import re

import pytest

from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.prompts import PROMPTS, get_prompt, list_prompts
from ameriflux_mcp.registry import get_registered_tools
from ameriflux_mcp.resources import known_uris
from ameriflux_mcp.server import AmeriFluxServer
from tests.helpers.asgi import AppHarness, rpc

ALL_ARGS = {
    "cite_flux_data": {"sites": "US-Ha1, CA-Let", "product": "base"},
    "find_flux_sites": {
        "question": "How does drought change GPP in semi-arid grasslands?",
        "region": "New Mexico",
        "ecosystem": "GRA",
        "years": "2010:2020",
        "variables": "GPP, SWC",
    },
    "plan_site_analysis": {
        "sites": "US-Seg,US-Ses",
        "product": "FLUXNET-1F",
        "variables": "NEE_VUT_REF, GPP_NT_VUT_REF",
        "years": "2012-2018",
    },
}


def text(name: str, args: dict[str, str]) -> str:
    content = get_prompt(name, args).messages[0].content
    assert content.type == "text"
    return content.text


def test_listing() -> None:
    prompts = list_prompts()
    assert [p.name for p in prompts] == ["cite_flux_data", "find_flux_sites", "plan_site_analysis"]
    required = {p.name: [a.name for a in p.arguments or [] if a.required] for p in prompts}
    assert required == {
        "cite_flux_data": ["sites"],
        "find_flux_sites": ["question"],
        "plan_site_analysis": ["sites"],
    }


def test_rendering() -> None:
    find = text("find_flux_sites", ALL_ARGS["find_flux_sites"])
    assert "semi-arid" in find and "Region: New Mexico" in find and "Years: 2010-2020" in find
    assert "Do not download anything" in find
    plan = text("plan_site_analysis", ALL_ARGS["plan_site_analysis"])
    assert "sites=['US-Seg', 'US-Ses']" in plan and "product='FLUXNET'" in plan
    assert "names=['NEE_VUT_REF', 'GPP_NT_VUT_REF'], resolution='DD'" in plan
    assert "WITHOUT confirm" in plan and "explicitly agrees" in plan
    assert "never write the intended use" in plan
    cite = text("cite_flux_data", ALL_ARGS["cite_flux_data"])
    assert "product='BASE-BADM'" in cite and "include_bibtex=true" in cite
    minimal = text("find_flux_sites", {"question": "Where are CH4 towers?"})
    assert "Region" not in minimal


def test_fluxnet2015_analysis_never_downloads() -> None:
    plan = text("plan_site_analysis", {"sites": "US-Ha1", "product": "FLUXNET2015"})
    assert "amf_download_data" not in plan
    assert "ameriflux://guide/fluxnet2015-access" in plan


@pytest.mark.parametrize("name", [p.name for p in PROMPTS])
def test_recipes_name_only_real_tools_and_resources(name: str) -> None:
    body = text(name, ALL_ARGS[name])
    tools = {s.name for s in get_registered_tools()}
    for tool in re.findall(r"\bamf_[a-z_]+\b", body):
        assert tool in tools, tool
    uris = set(known_uris())
    for uri in re.findall(r"ameriflux://[a-z0-9/_-]+", body):
        assert uri in uris, uri


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("find_flux_sites", {}),
        ("cite_flux_data", {"sites": "US-Ha1", "bogus": "1"}),
        ("cite_flux_data", {"sites": "US-Ha1", "product": "FLUXNET-CH4"}),
        ("plan_site_analysis", {"sites": "US-Ha1", "product": "BIF"}),
        ("plan_site_analysis", {"sites": ",".join(f"US-A{i:02d}" for i in range(21))}),
        ("plan_site_analysis", {"sites": "US-Ha1; rm -rf"}),
        ("plan_site_analysis", {"sites": "US-Ha1", "years": "last decade"}),
        ("nope", {}),
    ],
)
def test_validation(name: str, args: dict[str, str]) -> None:
    with pytest.raises(ToolError):
        get_prompt(name, args)


async def test_prompts_over_http(http_server: AmeriFluxServer) -> None:
    async with AppHarness(http_server) as client:
        _, listed = await rpc(client, "prompts/list")
        _, got = await rpc(
            client,
            "prompts/get",
            {"name": "cite_flux_data", "arguments": {"sites": "US-Ha1"}},
            name="cite_flux_data",
        )
        _, bad = await rpc(client, "prompts/get", {"name": "nope"}, name="nope")
    assert [p["name"] for p in listed["result"]["prompts"]] == [
        "cite_flux_data",
        "find_flux_sites",
        "plan_site_analysis",
    ]
    assert "amf_get_citation" in got["result"]["messages"][0]["content"]["text"]
    assert "error" in bad
