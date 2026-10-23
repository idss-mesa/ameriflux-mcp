"""Stateless Streamable HTTP at ``/mcp`` (MCP 2026-07-28).

The SDK builds the Starlette app (``Server.streamable_http_app`` with
``stateless_http=True``: no session header, any instance answers any
request). ameriflux-mcp adds ``/healthz`` + ``/readyz`` routes and one raw ASGI
middleware that assigns a request id and binds it for logging. No header is
ever read as an identity and the MCP-level ``Authorization`` header is never
forwarded upstream: a hosted server never acts for a user (DESIGN.md D25), so
the download and local-file tools are not even listed over HTTP. Upstream-client
lifecycle is owned by :func:`app_lifecycle` around uvicorn, never by mutating
Starlette internals.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import structlog
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from ameriflux_mcp.config import ServerConfig
from ameriflux_mcp.context import current_request_headers, current_request_id, current_transport
from ameriflux_mcp.transport.healthz import healthz, readyz

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from ameriflux_mcp.server import AmeriFluxServer

MCP_PATH = "/mcp"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
log = structlog.get_logger("ameriflux_mcp.http")


def transport_security(cfg: ServerConfig) -> TransportSecuritySettings | None:
    """DNS-rebinding settings from config; ``None`` leaves the SDK default."""
    hosts = list(cfg.allowed_hosts)
    origins = list(cfg.allowed_origins)
    if cfg.public_base_url:
        parts = urlsplit(cfg.public_base_url)
        if parts.netloc:
            if parts.netloc not in hosts:
                hosts.append(parts.netloc)
            origin = f"{parts.scheme}://{parts.netloc}"
            if origin not in origins:
                origins.append(origin)
    if cfg.dns_rebinding_protection is False:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    if hosts or origins or cfg.dns_rebinding_protection:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
        )
    return None


class RequestContextMiddleware:
    """Raw ASGI middleware: request id, headers for routing, contextvars, log binding."""

    def __init__(self, app: ASGIApp, *, server: AmeriFluxServer) -> None:
        self.app = app
        self.server = server

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == MCP_PATH + "/":  # serve /mcp/ directly instead of a 307 redirect
            scope = {**scope, "path": MCP_PATH, "raw_path": MCP_PATH.encode("ascii")}
        if scope.get("path") == MCP_PATH and scope.get("method") in ("GET", "DELETE"):
            # Stateless and without server-initiated messages: no standalone SSE stream and no
            # session to delete. Both protocol eras allow 405 here; it also stops idle GET
            # streams from pinning connections.
            await _method_not_allowed(send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        supplied = headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.match(supplied) else uuid.uuid4().hex[:16]

        tokens = (
            current_transport.set("http"),
            current_request_id.set(request_id),
            current_request_headers.set(headers),
        )
        structlog.contextvars.bind_contextvars(
            request_id=request_id, path=scope.get("path"), method=scope.get("method")
        )

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = list(message.get("headers", []))
                raw.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": raw}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            current_request_headers.reset(tokens[2])
            current_request_id.reset(tokens[1])
            current_transport.reset(tokens[0])
            structlog.contextvars.unbind_contextvars("request_id", "path", "method")


async def _method_not_allowed(send: Send) -> None:
    body = b'{"error":"method_not_allowed","detail":"POST JSON-RPC requests to /mcp"}'
    await send(
        {
            "type": "http.response.start",
            "status": 405,
            "headers": [
                (b"content-type", b"application/json"),
                (b"allow", b"POST"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def build_http_app(server: AmeriFluxServer) -> Starlette:
    cfg = server.config.server
    mcp_server = server.build_mcp_server()
    app = mcp_server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=cfg.json_response,
        max_request_body_size=cfg.max_request_body_size,
        host=cfg.bind_address,
        transport_security=transport_security(cfg),
        custom_starlette_routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
        ],
    )
    app.state.ameriflux_server = server
    app.state.mcp_server = mcp_server
    app.add_middleware(RequestContextMiddleware, server=server)
    return app


@asynccontextmanager
async def app_lifecycle(server: AmeriFluxServer) -> AsyncIterator[None]:
    """Owns upstream resources around the HTTP server; closes them on exit."""
    try:
        yield
    finally:
        await server.aclose()


async def serve_http(server: AmeriFluxServer) -> None:
    import uvicorn

    cfg = server.config.server
    app = build_http_app(server)
    async with app_lifecycle(server):
        config = uvicorn.Config(
            app,
            host=cfg.bind_address,
            port=cfg.bind_port,
            log_level=cfg.log_level,
            lifespan="on",
            proxy_headers=True,
            server_header=False,
        )
        await uvicorn.Server(config).serve()


__all__: list[Any] = ["app_lifecycle", "build_http_app", "serve_http", "transport_security"]
