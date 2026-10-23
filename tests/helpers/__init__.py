"""Shared test helpers: a test identity, calling tools and validating their results."""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from ameriflux_mcp.registry import get_tool
from ameriflux_mcp.server import AmeriFluxServer

__all__ = ["IDENTITY_ENV", "PRIVATE_VALUES", "call_err", "call_ok", "output_schema"]

#: A complete download identity, as the plain environment variables.
IDENTITY_ENV: dict[str, str] = {
    "AMERIFLUX_USER_ID": "fluxtester42",
    "AMERIFLUX_USER_EMAIL": "flux.tester@example.org",
    "AMERIFLUX_USER_NAME": "Flux Tester",
    "AMERIFLUX_INTENDED_USE": "4",
    "AMERIFLUX_DESCRIPTION": "Testing ameriflux-mcp in a sandbox; not a real request.",
    "AMERIFLUX_MCP_IDENTITY__IS_TEST": "true",
}
#: Values that must never appear in any output.
PRIVATE_VALUES: tuple[str, ...] = ("fluxtester42", "flux.tester@example.org", "Flux Tester")


def output_schema(name: str) -> dict[str, Any]:
    return AmeriFluxServer.output_schema(get_tool(name))


async def call_ok(
    server: AmeriFluxServer, name: str, args: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    """Call a tool, assert success, and validate the payload against its outputSchema."""
    outcome = await server.call(name, args or {}, **kw)
    assert outcome.input_required is None, "unexpected input_required"
    assert not outcome.is_error, json.dumps(outcome.payload, indent=1)[:3000]
    jsonschema.Draft202012Validator(output_schema(name)).validate(outcome.payload)
    return outcome.payload


async def call_err(
    server: AmeriFluxServer, name: str, args: dict[str, Any] | None, code: str, **kw: Any
) -> dict[str, Any]:
    """Call a tool, assert it failed with ``code``; return the error object."""
    outcome = await server.call(name, args or {}, **kw)
    assert outcome.is_error, json.dumps(outcome.payload)[:2000]
    error: dict[str, Any] = outcome.payload["error"]
    assert error["code"] == code, error
    return error
