from __future__ import annotations

from collections.abc import Callable

from ameriflux_mcp.server import AmeriFluxServer
from tests.helpers import PRIVATE_VALUES
from tests.helpers.asgi import AppHarness


async def test_healthz_and_readyz_are_public_and_identity_free(
    make_server: Callable[..., AmeriFluxServer],
) -> None:
    server = make_server(transport="http", identity=True)
    async with AppHarness(server) as client:
        response = await client.get("/healthz")
        ready = await client.get("/readyz")
    body = response.json()
    assert response.status_code == 200
    assert (
        body["status"] == "ok"
        and body["protocolVersion"] == "2026-07-28"
        and body["transport"] == "http"
    )
    for value in PRIVATE_VALUES:
        assert value not in response.text and value not in ready.text
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "degraded": False}


async def test_readyz_warming_and_degraded(http_server: AmeriFluxServer) -> None:
    async with AppHarness(http_server) as client:
        http_server.readiness = "warming"
        warming = await client.get("/readyz")
        http_server.readiness = "degraded"
        degraded = await client.get("/readyz")
    assert warming.status_code == 503 and warming.json() == {"status": "warming"}
    assert degraded.status_code == 200 and degraded.json()["degraded"] is True
