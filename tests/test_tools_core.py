from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import PRIVATE_VALUES, call_ok


async def test_ping_without_identity(server: AmeriFluxServer) -> None:
    payload = await call_ok(server, "amf_ping")
    assert payload["pong"] == "ok"
    assert payload["protocolVersion"] == "2026-07-28" and payload["transport"] == "stdio"
    identity = payload["identity"]
    assert identity["available"] is False and identity["reason"] == "incomplete"
    assert identity["userIdConfigured"] is False and identity["isTestSet"] is False
    assert payload["downloadsEnabled"] is True and payload["downloadDir"]
    assert payload["localRoots"] == [payload["downloadDir"]]
    assert payload["endpoints"]["api"] == "https://amfcdn.lbl.gov/api"
    assert any("site PIs" in note for note in payload["notes"])
    assert any("ameriflux://guide/identity" in step for step in payload["nextSteps"])
    assert payload["source"] == {
        "endpoints": [],
        "backend": "local",
        "cached": False,
        "derived": [],
    }


async def test_ping_with_identity_reports_booleans_only(identity_server: AmeriFluxServer) -> None:
    payload = await call_ok(identity_server, "amf_ping")
    identity = payload["identity"]
    assert identity["available"] is True and identity["reason"] == "ok"
    assert (
        identity["userIdConfigured"] and identity["emailConfigured"] and identity["nameConfigured"]
    )
    assert identity["profiles"] == ["default"] and identity["completeProfiles"] == ["default"]
    assert identity["isTestSet"] is True and identity["isTest"] is True
    assert payload["notes"] == []
    text = json.dumps(payload)
    for value in PRIVATE_VALUES:
        assert value not in text


async def test_ping_notes_unset_is_test(
    make_server: Callable[..., AmeriFluxServer], identity_config: Config
) -> None:
    cfg = identity_config.model_copy(deep=True)
    cfg.identity.is_test = None
    server = make_server(config=cfg)
    payload = await call_ok(server, "amf_ping")
    assert payload["identity"]["available"] is True and payload["identity"]["isTestSet"] is False
    assert any("IS_TEST is unset" in note for note in payload["notes"])


async def test_ping_over_http(http_server: AmeriFluxServer) -> None:
    payload = await call_ok(http_server, "amf_ping")
    assert payload["transport"] == "http"
    assert payload["downloadsEnabled"] is False
    assert "downloadDir" not in payload and "localRoots" not in payload
    assert payload["identity"]["reason"] == "http"
    assert any("Hosted (HTTP) server" in note for note in payload["notes"])


async def test_ping_rejects_unknown_arguments(server: AmeriFluxServer) -> None:
    outcome = await server.call("amf_ping", {"bogus": True})
    assert outcome.is_error and outcome.payload["error"]["code"] == "invalid_argument"


async def test_ping_makes_no_request_by_default(
    server: AmeriFluxServer, router: FixtureRouter
) -> None:
    payload = await call_ok(server, "amf_ping")
    assert "upstream" not in payload and router.calls == []


async def test_ping_check_api(server: AmeriFluxServer, router: FixtureRouter) -> None:
    payload = await call_ok(server, "amf_ping", {"check_api": True})
    upstream = payload["upstream"]
    assert upstream["ok"] is True and upstream["variables"] == 145
    assert upstream["endpoint"] == "GET amfcdn.lbl.gov/api/v1/fp_var"
    assert payload["source"]["backend"] == "amfcdn"
    assert payload["source"]["endpoints"] == ["GET amfcdn.lbl.gov/api/v1/fp_var"]
    call = router.calls[0]
    assert call.key == "GET amfcdn.lbl.gov/api/v1/fp_var?limits=True"
    assert call.headers["user-agent"].startswith("ameriflux-mcp/0.1.0 (+https://github.com/")


async def test_ping_check_api_sends_no_identity(
    identity_server: AmeriFluxServer, router: FixtureRouter
) -> None:
    await call_ok(identity_server, "amf_ping", {"check_api": True})
    sent = json.dumps([c.headers for c in router.calls]) + json.dumps([c.url for c in router.calls])
    for value in PRIVATE_VALUES:
        assert value not in sent


async def test_ping_check_api_reports_an_outage(
    server: AmeriFluxServer, router: FixtureRouter
) -> None:
    router.inject(httpx.ConnectError, times=3)
    payload = await call_ok(server, "amf_ping", {"check_api": True})
    assert payload["upstream"]["ok"] is False
    assert payload["upstream"]["error"]["code"] == "upstream_unavailable"


async def test_ping_check_api_reports_cloudflare_errors(
    server: AmeriFluxServer, router: FixtureRouter
) -> None:
    router.inject(Reply(521, b"origin down", "text/html"), times=3)
    payload = await call_ok(server, "amf_ping", {"check_api": True})
    assert payload["upstream"]["error"]["code"] == "upstream_unavailable"


async def test_ping_check_api_detects_drift(server: AmeriFluxServer, router: FixtureRouter) -> None:
    router.add("GET amfcdn.lbl.gov/api/v1/fp_var?limits=True", Reply.json({"values": []}))
    payload = await call_ok(server, "amf_ping", {"check_api": True})
    assert payload["upstream"]["ok"] is False
    assert payload["upstream"]["error"]["code"] == "upstream_error"
