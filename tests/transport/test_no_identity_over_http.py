"""A hosted (HTTP) server never acts with an identity (DESIGN.md D25).

Replaces edi-mcp's per-request key tests: there is no identity header to honour, the
operator's configured identity is never used or reported over HTTP, identity-bearing
and local-file tools are not listed, and nothing identifying reaches the wire or logs.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from ameriflux_mcp.logging import setup_logging
from ameriflux_mcp.registry import register_tool, unregister_tool
from ameriflux_mcp.server import AmeriFluxServer
from tests.helpers import IDENTITY_ENV, PRIVATE_VALUES
from tests.helpers.asgi import AppHarness, rpc
from tests.test_registry import EchoIn, EchoOut


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    yield
    setup_logging("warning", "stdio")


@pytest.fixture
def identity_tool() -> Iterator[None]:
    async def handler(args: EchoIn, ctx: Any) -> EchoOut:
        return EchoOut(product_code="ran")

    register_tool(
        "amf_test_needs_identity",
        title="T",
        description="Test. Next: none.",
        input_model=EchoIn,
        output_model=EchoOut,
        surface="data",
        endpoints=[],
        requires_key=True,
    )(handler)
    yield
    unregister_tool("amf_test_needs_identity")


async def _call(
    server: AmeriFluxServer, name: str, arguments: dict[str, Any], headers: dict[str, str]
) -> tuple[str, dict[str, Any]]:
    async with AppHarness(server) as client:
        response, message = await rpc(
            client, "tools/call", {"name": name, "arguments": arguments}, headers=headers
        )
    return response.text, message["result"]


IDENTITY_HEADERS = {
    "X-AmeriFlux-User-Id": "header-user",
    "X-AmeriFlux-User-Email": "header@example.org",
    "Authorization": "Bearer header-token",
}


async def test_configured_identity_is_neither_used_nor_reported(
    make_server: Callable[..., AmeriFluxServer],
) -> None:
    server = make_server(transport="http", identity=True)
    text, result = await _call(server, "amf_ping", {}, IDENTITY_HEADERS)
    identity = result["structuredContent"]["identity"]
    assert identity == {
        "available": False,
        "reason": "http",
        "userIdConfigured": False,
        "emailConfigured": False,
        "nameConfigured": False,
        "profiles": [],
        "completeProfiles": [],
        "isTestSet": False,
    }
    for value in (*PRIVATE_VALUES, "header-user", "header@example.org"):
        assert value not in text


async def test_identity_tools_refuse_over_http_even_with_headers(
    make_server: Callable[..., AmeriFluxServer], identity_tool: None
) -> None:
    server = make_server(transport="http", identity=True)
    _, result = await _call(
        server, "amf_test_needs_identity", {"product_code": "x"}, IDENTITY_HEADERS
    )
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "auth_required"


async def test_same_tool_runs_on_stdio_with_identity(
    identity_server: AmeriFluxServer, identity_tool: None
) -> None:
    outcome = await identity_server.call("amf_test_needs_identity", {"product_code": "x"})
    assert not outcome.is_error and outcome.payload["productCode"] == "ran"


async def test_nothing_identifying_is_logged(
    make_server: Callable[..., AmeriFluxServer], capsys: pytest.CaptureFixture[str]
) -> None:
    setup_logging("debug", "http")
    server = make_server(transport="http", identity=True)
    await _call(server, "amf_ping", {}, IDENTITY_HEADERS)
    captured = capsys.readouterr()
    assert "tool.call" in captured.err
    for value in PRIVATE_VALUES:
        assert value not in captured.err and value not in captured.out
    assert "header-token" not in captured.err


def test_identity_env_is_complete_for_these_tests() -> None:
    assert json.dumps(sorted(IDENTITY_ENV)).count("AMERIFLUX") == 6
