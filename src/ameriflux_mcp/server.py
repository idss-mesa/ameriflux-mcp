"""The MCP adapter: exposes the tool registry, resources and prompts over the SDK.

Targets the **MCP 2026-07-28** stateless core via the low-level
``mcp.server.Server`` (SDK 2.x constructor callbacks). The registry stays
SDK-agnostic; this module is the only SDK-coupled seam:

* ``tools/list`` is sorted, fixed per deployment (transport + downloads), and
  carries a public cache hint; every schema declares JSON Schema 2020-12.
* ``tools/call`` results carry compact JSON as text *and* ``structuredContent``
  plus ``io.ameriflux-mcp/upstream`` ``_meta`` (the SDK adds ``serverInfo``).
* A handler's :class:`~ameriflux_mcp.errors.InputRequired` becomes an MRTR
  ``InputRequiredResult``; its continuation travels as ``requestState`` (kept from
  edi-mcp for the protocol surface; no v0.1 tool elicits, DESIGN.md D13).
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx
import structlog
from mcp import types as t

from ameriflux_mcp import __version__
from ameriflux_mcp.ameriflux.client import AmeriFluxClient
from ameriflux_mcp.config import Config
from ameriflux_mcp.context import (
    Elicited,
    UpstreamStats,
    build_tool_context,
    current_request_id,
)
from ameriflux_mcp.errors import InputRequired, ToolError
from ameriflux_mcp.registry import (
    REQUEST_STATE_VERSION,
    ToolSpec,
    decode_request_state,
    encode_request_state,
    get_registered_tools,
    get_tool,
    invoke,
)

if TYPE_CHECKING:
    from mcp.server import Server

    from ameriflux_mcp.context import ToolContext

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
TOOLS_LIST_TTL_MS = 300_000
RESOURCES_LIST_TTL_MS = 3_600_000
PROMPTS_LIST_TTL_MS = 86_400_000
RESOURCE_READ_STATIC_TTL_MS = 86_400_000
RESOURCE_READ_DERIVED_TTL_MS = 3_600_000
DISCOVER_TTL_MS = 300_000

META_SURFACE = "io.ameriflux-mcp/surface"
META_REQUIRES_IDENTITY = "io.ameriflux-mcp/requiresIdentity"
META_ENDPOINTS = "io.ameriflux-mcp/endpoints"
META_STDIO_ONLY = "io.ameriflux-mcp/stdioOnly"
META_UPSTREAM = "io.ameriflux-mcp/upstream"

SERVER_DESCRIPTION = (
    "Find AmeriFlux and FLUXNET eddy-covariance flux towers, check data availability, describe "
    "FLUXNET variables, cite data under the right policy, download with consent and preview files."
)

log = structlog.get_logger("ameriflux_mcp.server")


@dataclass
class CallOutcome:
    payload: dict[str, Any]
    is_error: bool
    input_required: InputRequired | None
    stats: UpstreamStats
    request_state: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _dumps(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def compact_schema(schema: Any, keywords: tuple[str, ...]) -> Any:
    """Drop annotation keywords (string-valued only, so a property *named* ``title`` survives)."""
    if isinstance(schema, dict):
        return {
            k: compact_schema(v, keywords)
            for k, v in schema.items()
            if not (k in keywords and isinstance(v, str))
        }
    if isinstance(schema, list):
        return [compact_schema(v, keywords) for v in schema]
    return schema


_SCHEMA_MAPS = ("properties", "$defs", "patternProperties")
_SCHEMA_ONE = ("items", "additionalProperties", "not", "contains", "propertyNames")
_SCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
_NULL = {"type": "null"}


def fold_nullable(schema: Any, *, drop_null_defaults: bool) -> Any:
    """Shorten pydantic's ``anyOf: [{type: T, ...}, {type: null}]`` to ``type: [T, "null"]``
    (same meaning in JSON Schema 2020-12) and drop ``default: null``. Applied to output
    schemas only (edi-mcp D20): input schemas keep pydantic's shape, which every client handles.

    Keeps ``tools/list`` inside its byte bound. Branches with ``enum``/``const``/``$ref``
    are left alone, since folding ``null`` into them would change what validates.
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "default" and value is None and drop_null_defaults:
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {
                name: fold_nullable(sub, drop_null_defaults=drop_null_defaults)
                for name, sub in value.items()
            }
        elif key in _SCHEMA_ONE:
            out[key] = fold_nullable(value, drop_null_defaults=drop_null_defaults)
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            out[key] = [fold_nullable(s, drop_null_defaults=drop_null_defaults) for s in value]
        else:
            out[key] = value
    branches = out.get("anyOf")
    if isinstance(branches, list) and len(branches) == 2 and _NULL in branches:
        other = branches[0] if branches[1] == _NULL else branches[1]
        if (
            isinstance(other, dict)
            and isinstance(other.get("type"), str)
            and not ({"enum", "const", "$ref", "anyOf", "oneOf", "allOf"} & set(other))
            and not (set(other) & (set(out) - {"anyOf"}))
        ):
            del out["anyOf"]
            out.update(other)
            out["type"] = [other["type"], "null"]
    return out


def _plain_responses(responses: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """MRTR answers arrive as SDK models (``ElicitResult``); handlers get plain JSON."""
    if not responses:
        return None
    out: dict[str, Any] = {}
    for key, value in responses.items():
        dump = getattr(value, "model_dump", None)
        out[key] = dump(by_alias=True, exclude_none=True, mode="json") if callable(dump) else value
    return out


class AmeriFluxServer:
    """Process-wide server object; one per transport deployment."""

    def __init__(
        self,
        config: Config,
        *,
        transport: Literal["stdio", "http"],
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport: Literal["stdio", "http"] = transport
        #: The one upstream client; ``http_transport`` lets tests swap in a mock.
        self.client = AmeriFluxClient(config.upstream, http_transport=http_transport)
        #: Reported by ``/readyz``; ``degraded`` is set when startup checks fail.
        self.readiness: Literal["ready", "warming", "degraded"] = "ready"

    # ------------------------------------------------------------------ tools

    @property
    def downloads_enabled(self) -> bool:
        return self.config.effective_downloads_enabled(self.transport)

    @property
    def tools(self) -> list[ToolSpec]:
        return get_registered_tools(
            transport=self.transport, downloads_enabled=self.downloads_enabled
        )

    @staticmethod
    def input_schema(spec: ToolSpec) -> dict[str, Any]:
        """Validation schema by alias; pydantic's auto titles dropped, descriptions kept for the model."""
        raw = spec.input_model.model_json_schema(by_alias=True, mode="validation")
        schema: dict[str, Any] = dict(compact_schema(raw, ("title",)))
        schema["$schema"] = JSON_SCHEMA_DIALECT
        return schema

    @staticmethod
    def output_schema(spec: ToolSpec) -> dict[str, Any]:
        """Serialization schema by alias, without titles/descriptions (docs render them from the models)."""
        raw = spec.output_model.model_json_schema(by_alias=True, mode="serialization")
        schema: dict[str, Any] = fold_nullable(
            compact_schema(raw, ("title", "description")), drop_null_defaults=True
        )
        schema["$schema"] = JSON_SCHEMA_DIALECT
        return schema

    def tool_definitions(self) -> list[t.Tool]:
        out: list[t.Tool] = []
        for spec in self.tools:
            meta: dict[str, Any] = {
                META_SURFACE: spec.surface,
                META_REQUIRES_IDENTITY: spec.requires_key,
                META_ENDPOINTS: list(spec.endpoints),
            }
            if "http" not in spec.transports:
                meta[META_STDIO_ONLY] = True
            out.append(
                t.Tool(
                    name=spec.name,
                    title=spec.title,
                    description=spec.description,
                    input_schema=self.input_schema(spec),
                    output_schema=self.output_schema(spec),
                    annotations=t.ToolAnnotations(
                        title=spec.title,
                        read_only_hint=spec.read_only,
                        destructive_hint=spec.destructive,
                        idempotent_hint=spec.idempotent,
                        open_world_hint=spec.open_world,
                    ),
                    meta=meta,
                )
            )
        return out

    def tool_context(
        self,
        tool_name: str,
        *,
        client_capabilities: Mapping[str, Any] | None = None,
        elicited: Elicited | None = None,
        request_id: str | None = None,
        stats: UpstreamStats | None = None,
    ) -> ToolContext:
        return build_tool_context(
            config=self.config,
            transport=self.transport,
            tool_name=tool_name,
            client_capabilities=client_capabilities,
            elicited=elicited,
            request_id=request_id,
            stats=stats,
            client=self.client,
        )

    async def call(
        self,
        name: str,
        args: Mapping[str, Any] | None = None,
        *,
        input_responses: Mapping[str, Any] | None = None,
        request_state: str | None = None,
        client_capabilities: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> CallOutcome:
        """Run one tool call in-process (the adapter, tests and ``--check`` use this)."""
        stats = UpstreamStats()
        started = time.monotonic()
        outcome: CallOutcome
        try:
            spec = get_tool(name)
        except KeyError:
            err = ToolError(
                "unknown_tool",
                f"No tool named {name!r}.",
                details={"name": name, "available": [s.name for s in self.tools]},
            )
            return CallOutcome(err.to_payload(), True, None, stats)
        try:
            elicited = None
            if input_responses:
                state = decode_request_state(request_state or "", expected_tool=name)
                elicited = Elicited(responses=dict(input_responses), state=state)
            ctx = self.tool_context(
                name,
                client_capabilities=client_capabilities,
                elicited=elicited,
                request_id=request_id,
                stats=stats,
            )
            payload = await invoke(spec, args, ctx)
            outcome = CallOutcome(payload, False, None, stats)
        except InputRequired as pending:
            state = {
                "v": REQUEST_STATE_VERSION,
                "tool": name,
                "issuedAt": time.time(),
                **pending.state,
            }
            outcome = CallOutcome(
                {}, False, pending, stats, request_state=encode_request_state(state)
            )
        except ToolError as exc:
            outcome = CallOutcome(exc.to_payload(), True, None, stats)
        except Exception:
            log.exception("tool.crash", tool=name, request_id=request_id)
            err = ToolError(
                "internal_error",
                "The tool failed unexpectedly; the error was logged on the server.",
                details={"correlationId": request_id},
            )
            outcome = CallOutcome(err.to_payload(), True, None, stats)
        log.info(
            "tool.call",
            tool=name,
            ms=round((time.monotonic() - started) * 1000, 1),
            ok=not outcome.is_error,
            code=(outcome.payload.get("error") or {}).get("code") if outcome.is_error else None,
            result_bytes=len(_dumps(outcome.payload)),
            upstream_requests=stats.requests,
            cache_hits=stats.cache_hits,
            backend=stats.backend,
            request_id=request_id,
        )
        return outcome

    # ------------------------------------------------------------------ MCP

    def build_mcp_server(self) -> Server[Any]:
        from mcp.server import Server
        from mcp.server.caching import CacheHint
        from mcp.shared.exceptions import MCPError

        from ameriflux_mcp import prompts as prompt_mod
        from ameriflux_mcp import resources as resource_mod
        from ameriflux_mcp.instructions import SERVER_INSTRUCTIONS

        async def _on_list_tools(_ctx: Any, _params: Any = None) -> t.ListToolsResult:
            return t.ListToolsResult(tools=self.tool_definitions())

        async def _on_call_tool(
            ctx: Any, params: t.CallToolRequestParams
        ) -> t.CallToolResult | t.InputRequiredResult:
            meta = ctx.meta if isinstance(ctx.meta, Mapping) else {}
            caps = meta.get(t.CLIENT_CAPABILITIES_META_KEY)
            request_id = current_request_id.get() or (
                str(ctx.request_id) if ctx.request_id is not None else None
            )
            outcome = await self.call(
                params.name,
                params.arguments,
                input_responses=_plain_responses(params.input_responses),
                request_state=params.request_state,
                client_capabilities=caps if isinstance(caps, Mapping) else None,
                request_id=request_id,
            )
            if outcome.input_required is not None:
                pending = outcome.input_required
                return t.InputRequiredResult(
                    input_requests={
                        pending.key: t.ElicitRequest(
                            method="elicitation/create",
                            params=t.ElicitRequestFormParams(
                                mode="form",
                                message=pending.message,
                                requested_schema=pending.requested_schema,
                            ),
                        )
                    },
                    request_state=outcome.request_state,
                )
            return t.CallToolResult(
                content=[t.TextContent(type="text", text=_dumps(outcome.payload))],
                structured_content=outcome.payload,
                is_error=outcome.is_error,
                meta={META_UPSTREAM: outcome.stats.as_meta()},
            )

        async def _on_list_resources(_ctx: Any, _params: Any = None) -> t.ListResourcesResult:
            return t.ListResourcesResult(resources=resource_mod.list_resources())

        async def _on_list_resource_templates(
            _ctx: Any, _params: Any = None
        ) -> t.ListResourceTemplatesResult:
            return t.ListResourceTemplatesResult(
                resource_templates=resource_mod.list_resource_templates()
            )

        async def _on_read_resource(
            ctx: Any, params: t.ReadResourceRequestParams
        ) -> t.ReadResourceResult:
            uri = str(params.uri)
            tool_ctx = self.tool_context("resources/read")
            try:
                content = await resource_mod.read_resource(uri, tool_ctx, server=self)
            except ToolError as exc:
                raise MCPError(
                    t.INVALID_PARAMS,
                    exc.message,
                    data={
                        "code": exc.code,
                        **{k: v for k, v in exc.details.items() if k in ("didYouMean", "uri")},
                        **({"hint": exc.hint} if exc.hint else {}),
                    },
                ) from None
            return t.ReadResourceResult(
                contents=[
                    t.TextResourceContents(uri=uri, text=content.text, mime_type=content.mime_type)
                ],
                ttl_ms=content.ttl_ms,
                cache_scope=content.cache_scope,
            )

        async def _on_list_prompts(_ctx: Any, _params: Any = None) -> t.ListPromptsResult:
            return t.ListPromptsResult(prompts=prompt_mod.list_prompts())

        async def _on_get_prompt(_ctx: Any, params: t.GetPromptRequestParams) -> t.GetPromptResult:
            try:
                return prompt_mod.get_prompt(params.name, params.arguments)
            except ToolError as exc:
                raise MCPError(t.INVALID_PARAMS, exc.message, data={"code": exc.code}) from None

        instructions = SERVER_INSTRUCTIONS
        if self.config.server.instructions_extra:
            instructions += "\n\n" + self.config.server.instructions_extra
        return Server(
            "ameriflux-mcp",
            version=__version__,
            title="AmeriFlux and FLUXNET",
            description=SERVER_DESCRIPTION,
            instructions=instructions,
            website_url="https://github.com/idss-mesa/ameriflux-mcp",
            cache_hints={
                "tools/list": CacheHint(
                    ttl_ms=self.config.server.tools_list_ttl_ms, scope="public"
                ),
                "resources/list": CacheHint(ttl_ms=RESOURCES_LIST_TTL_MS, scope="public"),
                "resources/templates/list": CacheHint(ttl_ms=RESOURCES_LIST_TTL_MS, scope="public"),
                "resources/read": CacheHint(ttl_ms=RESOURCE_READ_DERIVED_TTL_MS, scope="public"),
                "prompts/list": CacheHint(ttl_ms=PROMPTS_LIST_TTL_MS, scope="public"),
                "server/discover": CacheHint(ttl_ms=DISCOVER_TTL_MS, scope="public"),
            },
            on_list_tools=_on_list_tools,
            on_call_tool=_on_call_tool,
            on_list_resources=_on_list_resources,
            on_list_resource_templates=_on_list_resource_templates,
            on_read_resource=_on_read_resource,
            on_list_prompts=_on_list_prompts,
            on_get_prompt=_on_get_prompt,
        )

    async def serve(self) -> None:
        if self.transport == "stdio":
            from ameriflux_mcp.transport.stdio import serve_stdio

            await serve_stdio(self)
        else:
            from ameriflux_mcp.transport.streamable_http import serve_http

            await serve_http(self)

    async def aclose(self) -> None:
        """Close the upstream HTTP client."""
        await self.client.aclose()


def create_server(
    config: Config,
    *,
    transport: Literal["stdio", "http"] | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> AmeriFluxServer:
    """Build the server for one transport; importing the tools package registers every tool."""
    from ameriflux_mcp import tools as _tools  # noqa: F401  (registration side effect)

    mode: Literal["stdio", "http"] = transport or config.server.transport
    return AmeriFluxServer(config, transport=mode, http_transport=http_transport)


def run(config: Config, transport: str | None = None) -> None:
    """Blocking entry point used by the CLI."""
    import anyio

    mode: Literal["stdio", "http"] = (
        "http" if (transport or config.server.transport) == "http" else "stdio"
    )
    server = create_server(config, transport=mode)
    anyio.run(server.serve)
