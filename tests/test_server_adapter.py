from __future__ import annotations

import time
from collections.abc import Callable, Iterator

import jsonschema
import pytest
from pydantic import Field

from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import InputRequired
from ameriflux_mcp.models.common import AmfInput, ToolResultBase
from ameriflux_mcp.registry import decode_request_state, register_tool, unregister_tool
from ameriflux_mcp.server import (
    JSON_SCHEMA_DIALECT,
    META_ENDPOINTS,
    META_REQUIRES_IDENTITY,
    META_SURFACE,
    AmeriFluxServer,
)
from tests.helpers import PRIVATE_VALUES


class PickIn(AmfInput):
    value: str | None = Field(None, description="Optional.")


class PickOut(ToolResultBase):
    chosen: str


@pytest.fixture
def pick_tool() -> Iterator[None]:
    async def handler(args: PickIn, ctx: ToolContext) -> PickOut:
        if ctx.elicited is None:
            raise InputRequired(
                key="choice",
                message="Pick one",
                requested_schema={
                    "type": "object",
                    "properties": {"choice": {"type": "string", "enum": ["a", "b"]}},
                },
                state={"field": "value", "candidates": ["a", "b"]},
            )
        response = ctx.elicited.responses["choice"]
        content = response.get("content", response)
        assert ctx.elicited.state["candidates"] == ["a", "b"]
        return PickOut(chosen=content["choice"])

    register_tool(
        "amf_test_pick",
        title="Pick",
        description="Pick. Next: done.",
        input_model=PickIn,
        output_model=PickOut,
        surface="core",
        endpoints=[],
        supports_mrtr=True,
    )(handler)
    yield
    unregister_tool("amf_test_pick")


def test_tool_definitions_are_sorted_and_complete(server: AmeriFluxServer) -> None:
    defs = server.tool_definitions()
    assert [d.name for d in defs] == sorted(d.name for d in defs)
    for d in defs:
        assert d.input_schema["$schema"] == JSON_SCHEMA_DIALECT
        assert d.output_schema is not None and d.output_schema["$schema"] == JSON_SCHEMA_DIALECT
        jsonschema.Draft202012Validator.check_schema(d.input_schema)
        jsonschema.Draft202012Validator.check_schema(d.output_schema)
        assert d.title and d.annotations is not None and d.annotations.title == d.title
        assert d.meta is not None and {META_SURFACE, META_REQUIRES_IDENTITY, META_ENDPOINTS} <= set(
            d.meta
        )
        wire = d.model_dump(by_alias=True, exclude_none=True)
        assert {"inputSchema", "outputSchema", "_meta", "annotations"} <= set(wire)


async def test_unknown_tool(server: AmeriFluxServer) -> None:
    outcome = await server.call("amf_nope", {})
    assert outcome.is_error
    assert outcome.payload["error"]["code"] == "unknown_tool"
    assert "amf_ping" in outcome.payload["error"]["details"]["available"]


async def test_input_required_round_trip(identity_server: AmeriFluxServer, pick_tool: None) -> None:
    first = await identity_server.call("amf_test_pick", {})
    assert first.input_required is not None and first.request_state
    for value in PRIVATE_VALUES:
        assert value not in first.request_state
    state = decode_request_state(first.request_state, expected_tool="amf_test_pick")
    assert state["v"] == 1 and state["tool"] == "amf_test_pick" and state["issuedAt"] <= time.time()
    second = await identity_server.call(
        "amf_test_pick",
        {},
        input_responses={"choice": {"action": "accept", "content": {"choice": "b"}}},
        request_state=first.request_state,
    )
    assert not second.is_error and second.payload["chosen"] == "b"


async def test_tampered_request_state_rejected(server: AmeriFluxServer, pick_tool: None) -> None:
    outcome = await server.call(
        "amf_test_pick", {}, input_responses={"choice": {}}, request_state="garbage"
    )
    assert outcome.payload["error"]["code"] == "invalid_argument"


async def test_crash_becomes_internal_error_without_traceback(server: AmeriFluxServer) -> None:
    async def handler(args: PickIn, ctx: ToolContext) -> PickOut:
        raise RuntimeError("secret internals")

    register_tool(
        "amf_test_crash",
        title="Crash",
        description="Crash. Next: none.",
        input_model=PickIn,
        output_model=PickOut,
        surface="core",
        endpoints=[],
    )(handler)
    try:
        outcome = await server.call("amf_test_crash", {}, request_id="req-42")
    finally:
        unregister_tool("amf_test_crash")
    error = outcome.payload["error"]
    assert error["code"] == "internal_error"
    assert error["details"]["correlationId"] == "req-42"
    assert "secret internals" not in str(outcome.payload)


def test_stdio_only_tools_hidden_over_http(make_server: Callable[..., AmeriFluxServer]) -> None:
    async def handler(args: PickIn, ctx: ToolContext) -> PickOut:
        return PickOut(chosen="x")

    register_tool(
        "amf_test_local",
        title="L",
        description="L. Next: none.",
        input_model=PickIn,
        output_model=PickOut,
        surface="data",
        endpoints=[],
        transports=("stdio",),
        needs_downloads=True,
    )(handler)
    try:
        stdio = make_server()
        http = make_server(transport="http")
        assert "amf_test_local" in [t.name for t in stdio.tools]
        assert "amf_test_local" not in [t.name for t in http.tools]
        local = next(d for d in stdio.tool_definitions() if d.name == "amf_test_local")
        assert local.meta is not None and local.meta["io.ameriflux-mcp/stdioOnly"] is True
    finally:
        unregister_tool("amf_test_local")
