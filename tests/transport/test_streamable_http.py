"""The Streamable HTTP boundary ameriflux-mcp owns: paths, limits, request ids, JSON mode."""

from __future__ import annotations

from collections.abc import Callable

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests.helpers.asgi import AppHarness, mcp_headers, rpc


def _http(
    make_server: Callable[..., AmeriFluxServer], config: Config, **server: object
) -> AmeriFluxServer:
    cfg = config.model_copy(deep=True)
    for key, value in server.items():
        setattr(cfg.server, key, value)
    return make_server(transport="http", config=cfg)


async def test_bare_and_slashed_paths_both_answer(http_server: AmeriFluxServer) -> None:
    async with AppHarness(http_server) as client:
        bare, _ = await rpc(client, "tools/list")
        slashed = await client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientCapabilities": {},
                    }
                },
            },
            headers=mcp_headers("tools/list"),
        )
    assert bare.status_code == 200 and slashed.status_code == 200


async def test_get_mcp_and_legacy_sse_routes(http_server: AmeriFluxServer) -> None:
    async with AppHarness(http_server) as client:
        get = await client.get("/mcp", headers={"Accept": "text/event-stream"})
        delete = await client.delete("/mcp")
        sse = await client.get("/sse")
        messages = await client.post("/messages/", json={})
    assert get.status_code == 405 and delete.status_code == 405 and get.headers["allow"] == "POST"
    assert sse.status_code == 404 and messages.status_code == 404


async def test_request_body_limit(
    make_server: Callable[..., AmeriFluxServer], config: Config
) -> None:
    server = _http(make_server, config, max_request_body_size=4096)
    async with AppHarness(server) as client:
        response = await client.post(
            "/mcp", content=b"{" + b" " * 10_000 + b"}", headers=mcp_headers("tools/list")
        )
    assert response.status_code == 413


async def test_request_id_is_echoed_or_generated(http_server: AmeriFluxServer) -> None:
    async with AppHarness(http_server) as client:
        given, _ = await rpc(client, "tools/list", headers={"X-Request-Id": "abc-123"})
        made, _ = await rpc(client, "tools/list", headers={"X-Request-Id": "bad id with spaces"})
    assert given.headers["x-request-id"] == "abc-123"
    assert (
        made.headers["x-request-id"] != "bad id with spaces"
        and len(made.headers["x-request-id"]) == 16
    )


async def test_json_response_mode(
    make_server: Callable[..., AmeriFluxServer], config: Config
) -> None:
    server = _http(make_server, config, json_response=True)
    async with AppHarness(server) as client:
        response, message = await rpc(client, "tools/call", {"name": "amf_ping", "arguments": {}})
    assert response.headers["content-type"].startswith("application/json")
    assert message["result"]["structuredContent"]["pong"] == "ok"


async def test_download_tool_absent_over_http(http_server: AmeriFluxServer) -> None:
    async with AppHarness(http_server) as client:
        _, message = await rpc(client, "tools/list")
    names = [t["name"] for t in message["result"]["tools"]]
    assert "amf_download_data" not in names and "amf_ping" in names
