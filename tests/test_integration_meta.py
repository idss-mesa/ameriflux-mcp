"""Whole-system checks: endpoints vs the allow-list, tests per tool, the end-to-end trace."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import ameriflux_mcp.tools  # noqa: F401  (registers every tool)
from ameriflux_mcp.ameriflux.client import ALLOWED, DATA_DOWNLOAD_PATH
from ameriflux_mcp.registry import get_registered_tools
from tests import archives
from tests.helpers import call_ok
from tests.test_tools_download import AR_BAL, FileServer, link, response

ROOT = Path(__file__).resolve().parents[1]

#: Tools without a live test, and why (they never use the network).
LIVE_EXEMPT: dict[str, str] = {
    "amf_list_files": "local files only (open_world=False)",
    "amf_read_bif": "local files only (open_world=False)",
}


def test_declared_endpoints_are_allow_listed() -> None:
    specs = get_registered_tools()
    assert len(specs) == 12
    for spec in specs:
        for endpoint in spec.endpoints:
            method, _, target = endpoint.partition(" ")
            host, _, path = target.partition("/")
            path = "/" + path.split("{", 1)[0]
            if method == "POST":
                assert (spec.name, host, path) == (
                    "amf_download_data",
                    "amfcdn.lbl.gov",
                    f"/api/{DATA_DOWNLOAD_PATH}",
                ), endpoint
                continue
            assert method in ("GET", "HEAD"), endpoint
            prefixes = ALLOWED.get(host)
            assert prefixes is not None, endpoint
            assert any(path.startswith(p) or p.startswith(path) for p in prefixes), endpoint
        if not spec.open_world:
            assert spec.endpoints == (), spec.name


def test_every_tool_has_unit_and_live_tests() -> None:
    unit = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "tests").rglob("test_*.py")
        if "live" not in p.parts and p.name != "test_integration_meta.py"
    )
    live = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "tests" / "live").glob("test_*.py")
    )
    specs = {s.name: s for s in get_registered_tools()}
    assert set(LIVE_EXEMPT) <= set(specs)
    for name, spec in specs.items():
        assert re.search(rf'"{name}"', unit), f"no unit test calls {name}"
        if name in LIVE_EXEMPT:
            assert spec.open_world is False, name
            continue
        assert re.search(rf'"{name}"', live), f"no live test calls {name}"


def test_identity_and_transport_sets() -> None:
    specs = get_registered_tools()
    assert [s.name for s in specs if s.requires_key] == ["amf_download_data"]
    assert {s.name for s in specs if "http" not in s.transports} == {
        "amf_download_data",
        "amf_list_files",
        "amf_preview_data",
        "amf_read_bif",
    }
    assert len(specs) == 12
    assert len(get_registered_tools(transport="http")) == 8
    assert [s.name for s in specs if not s.idempotent] == ["amf_download_data"]


async def test_design_trace(make_server: Callable[..., Any], router: Any, tmp_path: Path) -> None:
    """Plan step 7's agent script: search -> availability -> describe -> download -> preview -> cite."""
    files = FileServer(router)
    build = tmp_path / "build"
    build.mkdir()
    content = archives.fluxnet_zip(build).read_bytes()
    url = files.serve("FLUXNET", AR_BAL, content)
    files.response = response([link("AR-Bal", url, "FLUXNET", len(content))])
    server = make_server(identity=True)

    found = await call_ok(server, "amf_search_sites", {"query": "Balcarce"})
    site = found["sites"][0]["siteId"]
    assert site == "AR-Bal"
    avail = await call_ok(
        server, "amf_get_availability", {"sites": [site], "products": ["FLUXNET"]}
    )
    assert avail["rows"][0]["years"] == "2012-2013"
    described = await call_ok(
        server,
        "amf_describe_variables",
        {"names": ["NEE_VUT_REF"], "resolution": "DD"},
    )
    assert described["variables"][0]["name"] == "NEE_VUT_REF"
    plan = await call_ok(server, "amf_download_data", {"sites": [site], "product": "FLUXNET"})
    assert plan["ready"] and files.posts == []
    done = await call_ok(
        server,
        "amf_download_data",
        {
            "sites": [site],
            "product": "FLUXNET",
            "accept_data_policy": plan["policy"]["code"],
            "confirm": True,
        },
    )
    assert done["files"][0]["status"] == "downloaded" and len(files.posts) == 1
    preview = await call_ok(
        server,
        "amf_preview_data",
        {"site": site, "product": "FLUXNET", "resolution": "DD", "view": "subset"},
    )
    assert preview["fileInfo"]["stepMinutes"] == 1440
    cite = await call_ok(server, "amf_get_citation", {"sites": [site], "product": "FLUXNET"})
    assert "Ver." in cite["citations"][0]["citation"]
